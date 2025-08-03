import os
import uuid
import json
from pathlib import Path

import streamlit as st
from pydub import AudioSegment
import yt_dlp
from music21 import converter

# Try to import basic-pitch prediction functions
PREDICT_FN = None
PREDICT_AND_SAVE_FN = None
IMPORT_ERROR = None
try:
    from basic_pitch.inference import predict, predict_and_save

    PREDICT_FN = predict
    PREDICT_AND_SAVE_FN = predict_and_save
except ImportError as e:
    # try fallbacks individually
    try:
        from basic_pitch.inference import predict

        PREDICT_FN = predict
    except Exception:
        pass
    try:
        from basic_pitch.inference import predict_and_save

        PREDICT_AND_SAVE_FN = predict_and_save
    except Exception:
        pass
    IMPORT_ERROR = e
except Exception as e:
    IMPORT_ERROR = e

# Directories
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
            trimmed = audio[:30 * 1000]  # first 30s
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

    # Check import
    if not (PREDICT_FN or PREDICT_AND_SAVE_FN):
        st.error(f"Failed to import basic-pitch properly. {IMPORT_ERROR}")
        st.info(
            "basic-pitch needs a backend/model. Install a backend, e.g.:\n"
            "`pip install 'basic-pitch[tf]'` (with a compatible TensorFlow) or ensure ONNX/CoreML runtimes are installed."
        )
        midi_out = None
    else:
        try:
            # Prefer direct predict() since its return value structure is stable
            if PREDICT_FN:
                result = PREDICT_FN(str(audio_path), None)
                # expect (model_output, midi_data, note_events)
                if isinstance(result, tuple) and len(result) >= 3:
                    _, midi_data, note_events = result[0], result[1], result[2]
                else:
                    # fallback to unpack
                    model_output, midi_data, note_events = result
                # Save MIDI
                if hasattr(midi_data, "write"):
                    # e.g., pretty_midi.PrettyMIDI
                    midi_data.write(str(midi_out))
                else:
                    with open(midi_out, "wb") as f:
                        f.write(midi_data)
                # Save note events JSON if present
                with open(note_events_json, "w") as f:
                    json.dump(note_events, f, indent=2)
                st.success("🎼 MIDI generated via predict().")
            else:
                # Fallback to predict_and_save; try to infer signature
                import inspect

                sig = inspect.signature(PREDICT_AND_SAVE_FN)
                params = list(sig.parameters.keys())
                # heuristically supply save_midi and save_notes if expected
                if "save_midi" in params and "save_notes" in params:
                    # old-style: (audio_path, save_midi, save_notes, model_or_model_path)
                    PREDICT_AND_SAVE_FN(str(audio_path), str(midi_out), str(note_events_json), None)
                elif "save_model_outputs" in params and "save_notes" in params:
                    # try analogous
                    PREDICT_AND_SAVE_FN(str(audio_path), str(midi_out), str(note_events_json), None)
                else:
                    # fallback: naive
                    PREDICT_AND_SAVE_FN(str(audio_path), str(midi_out), str(note_events_json), None)
                st.success("🎼 MIDI generated via predict_and_save().")
        except Exception as e:
            st.error(f"❌ Error generating MIDI / prediction: {e}")
            st.info(
                "Hint: basic-pitch needs a working model backend. If it complains about loading None or unsupported formats, install the appropriate extras (e.g., `basic-pitch[tf]` with a supported TensorFlow)."
            )
            midi_out = None

        # Convert to MusicXML if MIDI exists
        if midi_out and midi_out.exists():
            try:
                score = converter.parse(str(midi_out))
                score.write("musicxml", fp=str(musicxml_path))
                st.success("✅ Sheet music exported as MusicXML.")
            except Exception as e:
                st.error(f"❌ Error converting MIDI to MusicXML: {e}")
                musicxml_path = None

    # Downloads
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
