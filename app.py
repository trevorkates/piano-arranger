import os
import uuid
import shutil
import streamlit as st
from pydub import AudioSegment
import yt_dlp
from music21 import converter

from basic_pitch.inference import predict_and_save, load_model

# Create folders
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Load model once at startup
model = load_model()

st.set_page_config(page_title="AI Piano Arranger", layout="centered")
st.title("🎼 AI Piano Arranger")
st.markdown("""
Upload a short audio file or paste a YouTube link.  
We'll generate a solo piano arrangement as sheet music!
""")

input_type = st.radio("Select input type:", ["Upload File", "YouTube Link"])

def generate_sheet_music(audio_path, unique_id):
    with st.spinner("Analyzing..."):
        predict_and_save(
            audio_path,
            OUTPUT_FOLDER,
            model_or_model_path=model,
            save_midi=True,
            save_notes=False,
            sonify_midi=False,
        )

    midi_path = os.path.join(OUTPUT_FOLDER, f"{unique_id}.mid")
    pdf_path = os.path.join(OUTPUT_FOLDER, f"{unique_id}.pdf")
    score = converter.parse(midi_path)
    score.write("lily.pdf", fp=pdf_path)
    st.download_button("Download PDF Sheet Music", data=open(pdf_path, "rb"), file_name="arrangement.pdf")

if input_type == "Upload File":
    uploaded_file = st.file_uploader("Upload audio file (MP3/WAV)", type=["mp3", "wav"])
    if uploaded_file and st.button("Convert to Sheet Music"):
        unique_id = str(uuid.uuid4())
        audio_path = os.path.join(UPLOAD_FOLDER, f"{unique_id}.mp3")
        with open(audio_path, "wb") as f:
            f.write(uploaded_file.read())
        st.success("✅ File uploaded successfully. Generating sheet music...")
        generate_sheet_music(audio_path, unique_id)

elif input_type == "YouTube Link":
    url = st.text_input("Paste YouTube link here")
    if url and st.button("Download and Convert"):
        unique_id = str(uuid.uuid4())
        base_path = os.path.join(UPLOAD_FOLDER, f"{unique_id}")
        output_path = f"{base_path}.mp3"

        yt_opts = {
            "format": "bestaudio/best",
            "outtmpl": base_path,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "postprocessor_args": [
                "-ss", "00:00:00", "-t", "00:00:30"  # trim to 30 seconds
            ],
            "quiet": True,
        }

        try:
            with yt_dlp.YoutubeDL(yt_opts) as ydl:
                ydl.download([url])

            final_path = output_path if os.path.exists(output_path) else output_path + ".mp3"
            if not os.path.exists(final_path):
                raise FileNotFoundError(f"Audio not found at {final_path}")

            st.success("✅ Downloaded and trimmed audio. Generating sheet music...")
            generate_sheet_music(final_path, unique_id)

        except Exception as e:
            st.error(f"❌ Error downloading or processing audio: {e}")
