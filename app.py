import os
import uuid
import json
from pathlib import Path

import streamlit as st
from pydub import AudioSegment
import yt_dlp
from music21 import converter

try:
    from basic_pitch.inference import predict  # correct API
except ImportError as e:
    predict = None
    PREDICT_IMPORT_ERROR = e
else:
    PREDICT_IMPORT_ERROR = None

# Ensure output directories exist
UPLOADS = Path("uploads")
OUTPUTS = Path("outputs")
for d in (UPLOADS, OUTPUTS):
    d.mkdir(exist_ok=True)

st.set_page_config(page_title="AI Piano Arranger", layout="wide")
st.title("🎹 AI Piano Arranger")
st.write("Upload a short audio file or paste a YouTube link. We'll generate a solo piano arrangement as sheet music!")

input_type = st.radio("Select input type:", ["Upload File", "YouTube Link"])

audio_path: Path | None = None

# === Input handling ===
if input_type == "Upload File":
    uploaded = st.file_uploader("Upload audio (WAV/MP3/etc.)", type=["wav", "mp3", "m4a", "flac", "ogg"])
    if uploaded:
        file_ext = Path(uploaded.name).suffix.lower()
        uid = str(uuid.uuid4())
        dest = UPLOADS / f"{uid}{file_ext}"
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
            trimmed = audio[:30 * 1000]  # first 30 seconds
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

# === Processing ===
if audio_path:
    st.success("✅ Audio ready. Generating sheet music...")

    if PREDICT_IMPORT_ERROR:
        st.error(f"Failed to import basic_pitch.predict: {PREDICT_IMPORT_ERROR}")
        st.info(
            "You need one of the supported backends installed (TensorFlow, ONNX, CoreML, or tflite-runtime) "
            "and a compatible basic-pitch version. See README for environment recommendations."
        )
    uid = audio_path.stem.split("_")[0]
    midi_out = OUTPUTS / f"{uid}.midi"
    musicxml_path = OUTPUTS / f"{uid}.musicxml"
    notes_json = OUTPUTS / f"{uid}_note_events.json"

    try:
        if not predict:
            raise RuntimeError("basic_pitch.predict is unavailable due to import failure.")
        model_output, midi_data, note_events = predict(str(audio_path), None)
        # Write MIDI file
        midi_data.write(str(midi_out))
        st.success("🎼 MIDI generated.")
        # Save note events
        try:
            with open(notes_json, "w") as f:
                json.dump(note_events, f, indent=2)
        except Exception:
            st.warning("Could not write note events JSON.")
    except Exception as e:
        st.error(f"❌ Error generating MIDI / prediction: {e}")
        st.info(
            "Hint: basic-pitch needs a supported model backend (CoreML, TFLite, ONNX, or TensorFlow). "
            "Make sure the appropriate extras are installed and compatible with your platform."
        )
        midi_out = None

    if midi_out and midi_out.exists():
        try:
            score = converter.parse(str(midi_out))
            score.write("musicxml", fp=str(musicxml_path))
            st.success("✅ Sheet music exported as MusicXML.")
        except Exception as e:
            st.error(f"❌ Error converting MIDI to MusicXML: {e}")
            musicxml_path = None

    # === Downloads UI ===
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
- To get **PDF sheet music**, open the `.musicxml` in MuseScore or use the MuseScore CLI.  
  Example:  
  ```sh
  musescore score.musicxml -o sheet.pdf
        """
    )
