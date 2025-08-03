import streamlit as st
import os
import uuid
import shutil
import tempfile

from pydub import AudioSegment
import yt_dlp
from music21 import converter, environment

from basic_pitch.inference import predict_and_save

# Setup Streamlit UI
st.set_page_config(page_title="🎹 AI Piano Arranger")
st.title("🎼 AI Piano Arranger")
st.write("Upload a short audio file or paste a YouTube link. We'll generate a solo piano arrangement as sheet music!")

# Create folders
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Helper: convert to WAV
def convert_to_wav(input_path, output_path):
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_channels(1).set_frame_rate(22050)
    audio.export(output_path, format="wav")

# Helper: convert MIDI to PDF sheet music
def midi_to_pdf(midi_path, pdf_path):
    score = converter.parse(midi_path)
    environment.set("musicxmlPath", "/usr/bin/lilypond")  # path is not used on Streamlit Cloud
    score.write("lily.pdf", fp=pdf_path)

# Process file or YouTube
audio_path = None
input_type = st.radio("Select input type:", ("Upload File", "YouTube Link"))

if input_type == "Upload File":
    uploaded_file = st.file_uploader("Upload audio (mp3, wav, etc.)", type=["mp3", "wav", "m4a", "flac"])
    if uploaded_file:
        file_ext = uploaded_file.name.split(".")[-1]
        file_id = str(uuid.uuid4())
        temp_path = os.path.join(UPLOAD_DIR, f"{file_id}.{file_ext}")
        with open(temp_path, "wb") as f:
            f.write(uploaded_file.read())

        wav_path = os.path.join(UPLOAD_DIR, f"{file_id}.wav")
        convert_to_wav(temp_path, wav_path)
        audio_path = wav_path

elif input_type == "YouTube Link":
    yt_url = st.text_input("Paste YouTube link here")
    if yt_url:
        if st.button("Download and Convert"):
            try:
                file_id = str(uuid.uuid4())
                temp_audio_path = os.path.join(UPLOAD_DIR, f"{file_id}.mp3")
                ydl_opts = {
                    "format": "bestaudio/best",
                    "outtmpl": temp_audio_path,
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([yt_url])

                wav_path = os.path.join(UPLOAD_DIR, f"{file_id}.wav")
                convert_to_wav(temp_audio_path, wav_path)
                audio_path = wav_path
                st.success("✅ Download complete. Click below to convert to sheet music.")
            except Exception as e:
                st.error(f"❌ Error downloading audio: {e}")

# Run model
if audio_path:
    if st.button("🎵 Convert to Sheet Music"):
        try:
            base = os.path.splitext(os.path.basename(audio_path))[0]
            midi_path = os.path.join(OUTPUT_DIR, f"{base}.mid")
            note_path = os.path.join(OUTPUT_DIR, f"{base}.txt")
            pdf_path = os.path.join(OUTPUT_DIR, f"{base}.pdf")

            st.info("🔍 Running AI model... please wait")
            predict_and_save(
                audio_path=audio_path,
                output_directory=OUTPUT_DIR,
                save_midi=True,
                save_model_outputs=False,
                save_notes=True,
            )

            # Convert MIDI to PDF
            midi_to_pdf(midi_path, pdf_path)

            st.success("✅ Done! Download your results below:")
            with open(midi_path, "rb") as f:
                st.download_button("🎼 Download MIDI", f, file_name="arrangement.mid")

            with open(pdf_path, "rb") as f:
                st.download_button("📄 Download Sheet Music PDF", f, file_name="arrangement.pdf")

        except Exception as e:
            st.error(f"❌ Error: {e}")
