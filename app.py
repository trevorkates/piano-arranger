import streamlit as st
import os
import uuid
import shutil
import tempfile

from basic_pitch.inference import predict_and_save
from pydub import AudioSegment
import yt_dlp
from music21 import converter

# --- CONFIG -------------------------------------------------------
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- UI -----------------------------------------------------------
st.title("🎹 AI Piano Arranger + Sheet Music Generator")
st.write("Upload an MP3/WAV file or paste a YouTube link to generate solo piano sheet music and MIDI.")

youtube_url = st.text_input("🎬 Paste YouTube link (optional)")
uploaded_file = st.file_uploader("🎧 Or upload an audio file", type=["mp3", "wav"])

input_path = None

# --- DOWNLOAD FROM YOUTUBE ---------------------------------------
def download_youtube_audio(url: str) -> str:
    temp_dir = tempfile.mkdtemp()
    output_path = os.path.join(temp_dir, "yt_audio.mp3")
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_path,
        "quiet": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return output_path

# --- HANDLE AUDIO INPUT ------------------------------------------
if youtube_url:
    st.info("⏬ Downloading YouTube audio...")
    try:
        yt_mp3 = download_youtube_audio(youtube_url)
        input_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}.wav")
        AudioSegment.from_file(yt_mp3, format="mp3").export(input_path, format="wav")
        st.success("✅ Downloaded and converted to WAV")
    except Exception as e:
        st.error(f"❌ Failed to download/process YouTube audio: {e}")

elif uploaded_file:
    input_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}.wav")
    try:
        if uploaded_file.name.endswith(".mp3"):
            AudioSegment.from_file(uploaded_file, format="mp3").export(input_path, format="wav")
        else:
            with open(input_path, "wb") as f:
                f.write(uploaded_file.read())
        st.success("✅ Uploaded and converted to WAV")
    except Exception as e:
        st.error(f"❌ Failed to process uploaded audio: {e}")

# --- PROCESS & DISPLAY OUTPUT ------------------------------------
if input_path:
    midi_out = os.path.join(OUTPUT_DIR, f"{uuid.uuid4()}.mid")
    pdf_out = midi_out.replace(".mid", ".pdf")

    with st.spinner("🎼 Transcribing to MIDI..."):
        predict_and_save(
            [input_path],
            output_directory=OUTPUT_DIR,
            save_midi=True,
            save_model_outputs=False,
            save_notes=False,
            sonify_midi=False,
        )

        # Find and rename the MIDI file
        for file in os.listdir(OUTPUT_DIR):
            if file.endswith(".mid") and "basic_pitch" in file:
                os.rename(os.path.join(OUTPUT_DIR, file), midi_out)

    st.success("✅ MIDI transcription complete!")

    # --- PDF CONVERSION ------------------------------------------
    try:
        with st.spinner("🖨️ Creating PDF sheet music..."):
            score = converter.parse(midi_out)
            score.write("lily.pdf", fp=pdf_out)
            st.success("📄 PDF generated successfully!")
    except Exception as e:
        st.error(f"❌ Failed to create PDF: {e}")

    # --- DOWNLOADS -----------------------------------------------
    with open(midi_out, "rb") as f:
        st.download_button("🎧 Download MIDI", f, file_name="arrangement.mid")

    if os.path.exists(pdf_out):
        with open(pdf_out, "rb") as f:
            st.download_button("📄 Download Sheet Music PDF", f, file_name="arrangement.pdf")

    if st.button("♻️ Reset App"):
        shutil.rmtree(UPLOAD_DIR)
        shutil.rmtree(OUTPUT_DIR)
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        st.experimental_rerun()
