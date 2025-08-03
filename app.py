import os
import uuid
import json
from pathlib import Path

import streamlit as st
from pydub import AudioSegment
import yt_dlp
from music21 import converter

# Try to import basic-pitch entrypoints, accommodating version differences.
PREDICT_FN = None
PREDICT_AND_SAVE_FN = None
IMPORT_ERROR = None
try:
    from basic_pitch.inference import predict, predict_and_save  # newer / older variants
    PREDICT_FN = predict
    PREDICT_AND_SAVE_FN = predict_and_save
except ImportError:
    try:
        from basic_pitch.inference import predict  # fallback if only predict exists
        PREDICT_FN = predict
    except ImportError as e:
        IMPORT_ERROR = e
        PREDICT_FN = None
        PREDICT_AND_SAVE_FN = None
except Exception as e:
    IMPORT_ERROR = e

# Ensure dirs
UPLOADS = Path("uploads")
OUTPUTS = Path("outputs")
for d in (UPLOADS, OUTPUTS):
    d.mkdir(exist_ok=True)

st.set_page_config(page_title="AI Piano Arranger", layout="wide")
st.title("🎹 AI Piano Arranger")
st.write("Upload a short audio file or paste a YouTube link. We'll generate a solo piano arrangement as sheet music!")

input_type = st.radio("Select input type:", ["Upload File", "YouTube Link"])

audio_path: Path | None = None

# Input
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

# Processing
if audio_path:
    st.success("✅ Audio ready. Generating sheet music...")

    uid = audio_path.stem.split("_")[0]
    midi_out = OUTPUTS / f"{uid}.midi"
    musicxml_path = OUTPUTS / f"{uid}.musicxml"
    notes_json = OUTPUTS / f"{uid}_note_events.json"

    # Check availability
    if IMPORT_ERROR:
        st.error(f"Failed to import basic-pitch: {IMPORT_ERROR}")
        st.info(
            "basic-pitch requires a supported model backend (TensorFlow, ONNX, CoreML, or tflite-runtime). "
            "On Apple Silicon you may need `tensorflow-macos` + `tensorflow-metal` or install a compatible backend. "
            "See documentation for installing `basic-pitch[tf]` or `basic-pitch[onnx]`."
        )
    else:
        try:
            # Prefer predict_and_save if exists, else use predict
            if PREDICT_AND_SAVE_FN:
                # old signature: predict_and_save(audio_path, save_midi, save_notes, model_or_model_path)
                PREDICT_AND_SAVE_FN(str(audio_path), str(midi_out), str(notes_json), None)
                st.success("🎼 MIDI (and note events) generated via predict_and_save.")
            elif PREDICT_FN:
                model_output, midi_data, note_events = PREDICT_FN(str(audio_path), None)
                # Write MIDI
                midi_data.write(str(midi_out))
                with open(notes_json, "w") as f:
                    json.dump(note_events, f, indent=2)
                st.success("🎼 MIDI generated via predict.")
            else:
                raise RuntimeError("No usable prediction function available.")
        except Exception as e:
            st.error(f"❌ Error generating MIDI / prediction: {e}")
            st.info(
                "Hint: basic-pitch needs a backend capable of loading its model file. "
                "If the error mentions inability to load `None`, install a backend: "
                "`pip install 'basic-pitch[tf]'` (if TensorFlow compatible) or ensure ONNX/CoreML is properly installed."
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
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if audio_path.exists():
            st.download_button(
                "Download trimmed audio",
                data=open(audio_path, "rb"),
                file_name=audio_path.name,
                mime="audio/wav",
            )
    with col2:
        if midi_out and midi_out.exists():
            st.download_button(
                "Download MIDI",
                data=open(midi_out, "rb"),
                file_name=midi_out.name,
                mime="audio/midi",
            )
    with col3:
        if musicxml_path and musicxml_path.exists():
            st.download_button(
                "Download MusicXML",
                data=open(musicxml_path, "rb"),
                file_name=musicxml_path.name,
                mime="application/xml",
            )
    with col4:
        if notes_json.exists():
            st.download_button(
                "Download note events (JSON)",
                data=open(notes_json, "rb"),
                file_name=notes_json.name,
                mime="application/json",
            )

    st.markdown(
        """
**Next steps / notes:**  
- To get **PDF sheet music**, open the `.musicxml` in MuseScore or use the MuseScore CLI:  
```sh
musescore score.musicxml -o sheet.pdf
        """
    )
