import streamlit as st
import os
import uuid
import shutil
import tempfile

from basic_pitch.inference import predict_and_save, load_model
from pydub import AudioSegment
import yt_dlp

# --- CONFIG -------------------------------------------------------
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- APP UI -------------------------------------------------------
st.title("🎹 AI Piano Arranger")
st.write("Upload an MP3/WAV file or paste a YouTube link to generate a solo piano MIDI.")

youtube_url = st.text_input("🎬 Paste YouTube link (optional)")
uploaded_file = st.file_uploader("Or upload an audio file", type=["mp3", "wav"])

input_path = None

# --- YOUTUBE DOWNLOAD ---------------------------------------------
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

# --- HANDLE AUDIO INPUT -------------------------------------------
if youtube_url:
    st.info("⏬ Downloading audio from YouTube...")
    try:
        yt_mp3_path = download_youtube_audio(youtube_url)
        input_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}.wav")
        mp3 = AudioSegment.from_file(yt_mp3_path, format="mp3")
        mp3.export(input_path, format="wav")
        st.success("✅ YouTube audio downloaded and converted to WAV")
    except Exception as e:
        st.error(f"❌ Failed to process YouTube audio: {e}")

elif uploaded_file:
    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}.wav")

    if uploaded_file.name.endswith(".mp3"):
        mp3 = AudioSegment.from_file(uploaded_file, format="mp3")
        mp3.export(input_path, format="wav")
    else:
        with open(input_path, "wb") as f:
            f.write(uploaded_file.read())

    st.success("✅ File uploaded and converted to WAV")

# --- TRANSCRIPTION ------------------------------------------------
if input_path:
    midi_output_path = os.path.join(OUTPUT_DIR, f"{uuid.uuid4()}.mid")
    model = load_model()

    with st.spinner("🎼 Transcribing audio to MIDI..."):
        predict_and_save(
            [input_path],
            output_directory=OUTPUT_DIR,
            model_or_model_path=model,
            save_midi=True,
            save_model_outputs=False,
            save_notes=False,
            sonify_midi=False,
        )

        # Rename the output MIDI to a predictable name
        for file in os.listdir(OUTPUT_DIR):
            if file.endswith(".mid") and "basic_pitch" in file:
                os.rename(os.path.join(OUTPUT_DIR, file), midi_output_path)

    st.success("🎉 Transcription complete!")

    with open(midi_output_path, "rb") as f:
        st.download_button("🎹 Download MIDI", f, file_name="piano_arrangement.mid")

    if st.button("♻️ Clear session"):
        shutil.rmtree(UPLOAD_DIR)
        shutil.rmtree(OUTPUT_DIR)
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        st.experimental_rerun()
