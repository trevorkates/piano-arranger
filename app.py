import os
import uuid
import json
import inspect
from pathlib import Path

import streamlit as st
from pydub import AudioSegment
import yt_dlp
from music21 import converter

# Attempt to import basic-pitch functions flexibly.
PREDICT_FN = None
PREDICT_AND_SAVE_FN = None
IMPORT_ERROR = None
try:
    from basic_pitch.inference import predict, predict_and_save

    PREDICT_FN = predict
    PREDICT_AND_SAVE_FN = predict_and_save
except ImportError as e:
    # Could not import one or both
    try:
        from basic_pitch.inference import predict_and_save

        PREDICT_AND_SAVE_FN = predict_and_save
    except Exception:
        IMPORT_ERROR = e
    try:
        from basic_pitch.inference import predict

        PREDICT_FN = predict
    except Exception:
        pass
except Exception as e:
    IMPORT_ERROR = e

# Setup folders
UPLOADS = Path("uploads")
OUTPUTS = Path("outputs")
for d in (UPLOADS, OUTPUTS):
    d.mkdir(exist_ok=True)

st.set_page_config(page_title="AI Piano Arranger", layout="wide")
st.title("🎹 AI Piano Arranger")
st.write("Upload a short audio file or paste a YouTube link. We'll generate a solo piano arrangement as sheet music!")

input_type = st.radio("Select input type:", ["Upload File", "YouTube Link"])

audio_path: Path | None = None

if input_type == "Upload File":
    uploaded = st.file_uploader("Upload audio (WAV/MP3/etc.)", type=["wav", "mp3", "m4a", "flac", "ogg"])
    if uploaded:
        ext = Path(uploaded.name).suffix.lower()
        uid = str(uuid.uuid4())
        dest = UPLOADS / f"{uid}{ext}"
        with open(dest, "wb") as f:
            f.write(uploaded.getbuffer())
        audio_path = dest

elif input_type == "YouTube Link":
    url = st.text_input("Paste YouTube link here")
    if st.button("Download and Convert") and url:
        uid = str(uuid.uuid4())
        try:
            st.info("Downloading from YouTube...")
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": str(UPLOADS / f"{uid}.%(ext)s"),
                "quiet": True,
                "no_warnings": True,
                "skip_download": False,
                "postprocessors": [
                    {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
                ],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                raw_fname = ydl.prepare_filename(info)
                if not raw_fname.lower().endswith(".mp3"):
                    raw_fname = str(Path(raw_fname).with_suffix(".mp3"))
                audio_raw = Path(raw_fname)
                if not audio_raw.exists():
                    raise FileNotFoundError(f"Expected downloaded file {audio_raw} missing")
            st.success("✅ Downloaded. Trimming to first 30 seconds...")
            audio = AudioSegment.from_file(audio_raw)
            trimmed = audio[:30 * 1000]
            trimmed_path = UPLOADS / f"{uid}_trimmed.wav"
            trimmed.export(trimmed_path, format="wav")
            audio_path = trimmed_path
            try:
                audio_raw.unlink()
            except Exception:
                pass
        except Exception as e:
            st.error(f"❌ Error downloading audio: {e}")
            audio_path = None

if audio_path:
    st.success("✅ Audio ready. Generating sheet music...")

    uid = audio_path.stem.split("_")[0]
    midi_out = OUTPUTS / f"{uid}.midi"
    musicxml_path = OUTPUTS / f"{uid}.musicxml"
    note_events_json = OUTPUTS / f"{uid}_note_events.json"

    # If import failure
    if IMPORT_ERROR and not (PREDICT_FN or PREDICT_AND_SAVE_FN):
        st.error(f"Failed to import basic-pitch: {IMPORT_ERROR}")
        st.info(
            "basic-pitch needs a backend capable of loading its model (TensorFlow, ONNX, CoreML, or tflite-runtime). "
            "Install e.g. `pip install 'basic-pitch[tf]'` on a compatible Python or ensure ONNX/CoreML runtimes are present."
        )
    else:
        try:
            # Prefer predict_and_save if available
            if PREDICT_AND_SAVE_FN:
                sig = inspect.signature(PREDICT_AND_SAVE_FN)
                params = list(sig.parameters.keys())

                # Heuristic dispatch based on parameter names
                if "save_midi" in params and "save_notes" in params and "model_or_model_path" in params:
                    # old style
                    PREDICT_AND_SAVE_FN(str(audio_path), str(midi_out), str(note_events_json), None)
                    st.success("🎼 MIDI generated via predict_and_save (old signature).")
                elif "save_model_outputs" in params and "save_notes" in params and "model_or_model_path" in params:
                    # new/renamed signature: assume first arg is audio, second is model outputs (we give midi), third is notes, fourth model
                    PREDICT_AND_SAVE_FN(str(audio_path), str(midi_out), str(note_events_json), None)
                    st.success("🎼 MIDI generated via predict_and_save (new-ish signature).")
                else:
                    # Fallback: try calling with 4 positional and hope for the best
                    PREDICT_AND_SAVE_FN(str(audio_path), str(midi_out), str(note_events_json), None)
                    st.success("🎼 MIDI generated via predict_and_save (fallback).")
                # note events file may or may not have been written; MIDI might be somewhere—assume midi_out.
            elif PREDICT_FN:
                # predict returns (model_output, midi_data, note_events)
                result = PREDICT_FN(str(audio_path), None)
                if isinstance(result, tuple) and len(result) >= 3:
                    _, midi_data, note_events = result[0], result[1], result[2]
                else:
                    # Some versions might differ; try unpacking safely
                    model_output, midi_data, note_events = result
                # Write MIDI if object has write, else assume bytes
                if hasattr(midi_data, "write"):
                    midi_data.write(str(midi_out))
                else:
                    with open(midi_out, "wb") as f:
                        f.write(midi_data)
                with open(note_events_json, "w") as f:
                    json.dump(note_events, f, indent=2)
                st.success("🎼 MIDI generated via predict().")
            else:
                raise RuntimeError("No usable basic-pitch prediction function found.")
        except Exception as e:
            st.error(f"❌ Error generating MIDI / prediction: {e}")
            st.info(
                "Hint: basic-pitch needs a model backend. If you see errors about loading None or unsupported model formats, install one: "
                "`pip install 'basic-pitch[tf]'` (with compatible TensorFlow) or ensure ONNX/CoreML runtimes are present."
            )
            midi_out = None

        # Convert MIDI -> MusicXML
        if midi_out and midi_out.exists():
            try:
                score = converter.parse(str(midi_out))
                score.write("musicxml", fp=str(musicxml_path))
                st.success("✅ Sheet music exported as MusicXML.")
            except Exception as e:
                st.error(f"❌ Error converting MIDI to MusicXML: {e}")
                musicxml_path = None

    # Downloads UI
    st.subheader("Downloads")
    cols = st.columns(4)
    if audio_path.exists():
        with cols[0]:
            st.download_button(
                "Download trimmed audio",
                data=open(audio_path, "rb"),
                file_name=audio_path.name,
                mime="audio/wav",
            )
    if midi_out and midi_out.exists():
        with cols[1]:
            st.download_button(
                "Download MIDI",
                data=open(midi_out, "rb"),
                file_name=midi_out.name,
                mime="audio/midi",
            )
    if musicxml_path and musicxml_path.exists():
        with cols[2]:
            st.download_button(
                "Download MusicXML",
                data=open(musicxml_path, "rb"),
                file_name=musicxml_path.name,
                mime="application/xml",
            )
    if note_events_json.exists():
        with cols[3]:
            st.download_button(
                "Download note events (JSON)",
                data=open(note_events_json, "rb"),
                file_name=note_events_json.name,
                mime="application/json",
            )

    st.markdown(
        """
**Next steps / notes:**  
- To get **PDF sheet music**, open the `.musicxml` in MuseScore or via CLI:  
```sh
musescore score.musicxml -o sheet.pdf
        """
    )
