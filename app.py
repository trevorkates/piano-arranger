import uuid
import shutil
from pathlib import Path

import streamlit as st
from pydub import AudioSegment
import yt_dlp
from music21 import converter

# basic-pitch (CoreML backend assumed)
from basic_pitch.inference import predict_and_save

# Directories
UPLOADS = Path("uploads")
OUTPUTS = Path("outputs")
for d in (UPLOADS, OUTPUTS):
    d.mkdir(exist_ok=True)

st.set_page_config(page_title="AI Piano Arranger", layout="wide")
st.title("🎹 AI Piano Arranger")
st.write("Upload a short audio file or paste a YouTube link. We'll generate a solo piano arrangement as sheet music!")

input_type = st.radio("Select input type:", ["Upload File", "YouTube Link"])
audio_path = None

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

if audio_path:
    st.success("✅ Audio ready. Generating sheet music...")

    uid = audio_path.stem.split("_")[0]
    midi_out = OUTPUTS / f"{uid}.midi"
    musicxml_out = OUTPUTS / f"{uid}.musicxml"
    note_events_json = OUTPUTS / f"{uid}_note_events.json"

    try:
        # Use basic-pitch's predict_and_save; omit model path to use bundled default.
        # Signature (as of 0.4.0): predict_and_save(audio_path, save_midi, save_notes, model_or_model_path)
        predict_and_save(str(audio_path), str(midi_out), str(note_events_json), None)
        st.success("🎼 MIDI generated.")
    except Exception as e:
        st.error(f"❌ Error generating MIDI / prediction: {e}")
        st.info(
            "Hint: basic-pitch needs a working model backend. On macOS this uses CoreML; ensure you installed with the extra "
            "`basic-pitch[coreml]` so the CoreML runtime is present."
        )
        midi_out = None

    if midi_out and midi_out.exists():
        try:
            score = converter.parse(str(midi_out))
            score.write("musicxml", fp=str(musicxml_out))
            st.success("✅ Sheet music exported as MusicXML.")
        except Exception as e:
            st.error(f"❌ Error converting MIDI to MusicXML: {e}")
            musicxml_out = None

    st.subheader("Downloads")
    cols = st.columns(4)
    if audio_path.exists():
        with cols[0]:
            st.download_button("Download trimmed audio", data=open(audio_path, "rb"), file_name=audio_path.name, mime="audio/wav")
    if midi_out and midi_out.exists():
        with cols[1]:
            st.download_button("Download MIDI", data=open(midi_out, "rb"), file_name=midi_out.name, mime="audio/midi")
    if musicxml_out and musicxml_out.exists():
        with cols[2]:
            st.download_button("Download MusicXML", data=open(musicxml_out, "rb"), file_name=musicxml_out.name, mime="application/xml")
    if note_events_json.exists():
        with cols[3]:
            st.download_button("Download note events (JSON)", data=open(note_events_json, "rb"), file_name=note_events_json.name, mime="application/json")

    st.markdown(
        """
**Next steps / notes:**  
- To get **PDF sheet music**, open the `.musicxml` in MuseScore or convert via CLI:  
```sh
musescore score.musicxml -o sheet.pdf
        """
    )
