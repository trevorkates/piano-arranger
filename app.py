# app.py
import streamlit as st
import os
import uuid
import shutil

from basic_pitch.inference import predict_and_save
from pydub import AudioSegment

UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"

st.title("🎹 AI Piano Arranger")
st.write("Upload a song and get a solo piano MIDI file.")

uploaded_file = st.file_uploader("Upload an MP3 or WAV file", type=["mp3", "wav"])
if uploaded_file:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    file_id = str(uuid.uuid4())
    input_path = os.path.join(UPLOAD_DIR, f"{file_id}.wav")

    # Convert MP3 to WAV if needed
    if uploaded_file.name.endswith(".mp3"):
        mp3 = AudioSegment.from_file(uploaded_file, format="mp3")
        mp3.export(input_path, format="wav")
    else:
        with open(input_path, "wb") as f:
            f.write(uploaded_file.read())

    st.success("✅ File uploaded and converted to WAV")

    # Transcribe audio to MIDI
    midi_output_path = os.path.join(OUTPUT_DIR, f"{file_id}.mid")
    with st.spinner("🎼 Transcribing..."):
        predict_and_save(
            [input_path],
            output_directory=OUTPUT_DIR,
            save_midi=True,
            save_model_outputs=False,
            sonify_midi=False,
        )
        for f in os.listdir(OUTPUT_DIR):
            if f.endswith(".mid") and "basic_pitch" in f:
                os.rename(os.path.join(OUTPUT_DIR, f), midi_output_path)

    st.success("🎉 Done! Download your solo piano MIDI:")

    with open(midi_output_path, "rb") as f:
        st.download_button("🎹 Download MIDI", f, file_name="piano_arrangement.mid")

    if st.button("♻️ Clear"):
        shutil.rmtree(UPLOAD_DIR)
        shutil.rmtree(OUTPUT_DIR)
        st.experimental_rerun()
