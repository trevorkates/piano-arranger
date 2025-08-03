import os
import uuid
import shutil
import tempfile
from pathlib import Path
from datetime import timedelta

import streamlit as st
from pydub import AudioSegment
import yt_dlp
from music21 import converter

from basic_pitch.inference import predict_and_save  # no load_model; using correct signature

# Ensure directories exist
UPLOADS = Path("uploads")
OUTPUTS = Path("outputs")
for d in (UPLOADS, OUTPUTS):
    d.mkdir(exist_ok=True)

st.set_page_config(page_title="AI Piano Arranger", layout="wide")

st.title("🎹 AI Piano Arranger")
st.write("Upload a short audio file or paste a YouTube link. We'll generate a solo piano arrangement as sheet music!")

input_type = st.radio("Select input type:", ["Upload File", "YouTube Link"])

audio_path: Path | None = None
tmp_audio_path = None

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
            st.success("Downloading from YouTube...")
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
                downloaded_fname = ydl.prepare_filename(info)
                # After postprocessing, the file has .mp3 appended
                if not downloaded_fname.lower().endswith(".mp3"):
                    downloaded_fname = str(Path(downloaded_fname).with_suffix(".mp3"))
                audio_raw = Path(downloaded_fname)
                if not audio_raw.exists():
                    raise FileNotFoundError(f"Expected downloaded file {audio_raw} missing")
            # Trim to first 30 seconds
            st.success("✅ Downloaded and trimming to first 30 seconds...")
            audio = AudioSegment.from_file(audio_raw)
            trimmed = audio[:30 * 1000]  # first 30 seconds
            trimmed_path = UPLOADS / f"{uid}_trimmed.wav"
            trimmed.export(trimmed_path, format="wav")
            audio_path = trimmed_path
            # optional cleanup of original
            try:
                audio_raw.unlink()
            except Exception:
                pass
        except Exception as e:
            st.error(f"❌ Error downloading audio: {e}")
            audio_path = None

if audio_path:
    st.success("✅ Audio ready. Generating sheet music...")

    # Prepare output filenames
    uid = audio_path.stem.split("_")[0]
    midi_out = OUTPUTS / f"{uid}.midi"
    notes_out = OUTPUTS / f"{uid}_notes.json"  # basic-pitch will try to write notes if asked
    # basic_pitch.predict_and_save signature: (audio_path, save_midi, save_notes, model_or_model_path)
    try:
        # The library will create its own .mid; we pass the output paths
        predict_and_save(str(audio_path), str(midi_out), str(notes_out), None)
    except Exception as e:
        st.error(f"❌ Error generating MIDI / prediction: {e}")
    else:
        st.success("🎼 MIDI generated. Converting to MusicXML sheet music...")

        # Convert MIDI to music21 stream
        try:
            score = converter.parse(str(midi_out))
            musicxml_path = OUTPUTS / f"{uid}.musicxml"
            score.write("musicxml", fp=str(musicxml_path))
            st.success("✅ Sheet music exported as MusicXML.")
        except Exception as e:
            st.error(f"❌ Error converting MIDI to MusicXML: {e}")
            musicxml_path = None

        # Display downloads
        st.subheader("Downloads")
        col1, col2, col3 = st.columns(3)
        with col1:
            if audio_path.exists():
                st.download_button("Download trimmed audio", data=open(audio_path, "rb"), file_name=audio_path.name)
        with col2:
            if midi_out.exists():
                st.download_button("Download MIDI", data=open(midi_out, "rb"), file_name=midi_out.name)
        with col3:
            if musicxml_path and musicxml_path.exists():
                st.download_button("Download MusicXML", data=open(musicxml_path, "rb"), file_name=musicxml_path.name)

        st.markdown(
            """
**Next steps / notes:**  
- To get **PDF sheet music**, open the `.musicxml` in MuseScore or convert via LilyPond/other tools.  
- If you have `lilypond` installed locally, you can convert MusicXML to PDF manually:  
  ```sh
  musecore score.musicxml -o sheet.pdf  # or use MuseScore GUI
