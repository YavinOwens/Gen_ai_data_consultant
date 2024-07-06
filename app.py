import os
import time
import streamlit as st
import sounddevice as sd
import wavio
from datetime import datetime
import openai
import requests
import json
import pandas as pd
import faiss
import numpy as np
from PyPDF2 import PdfReader

# Ensure directories exist
def ensure_directories(base_dir, sub_dir):
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    if not os.path.exists(sub_dir):
        os.makedirs(sub_dir)

# Record audio
def record_audio(filename, duration=10, fs=44100):
    st.write(f"Recording for {duration} seconds...")
    myrecording = sd.rec(int(duration * fs), samplerate=fs, channels=2)
    sd.wait()  # Wait until recording is finished
    wavio.write(filename, myrecording, fs, sampwidth=2)
    st.write(f"Recording saved as {filename}")

# Transcribe and analyze sentiment using Assembly AI
def transcribe_and_analyze_audio(file_path, assemblyai_api_key):
    headers = {
        "authorization": assemblyai_api_key,
        "content-type": "application/json"
    }
    upload_url = "https://api.assemblyai.com/v2/upload"
    transcript_url = "https://api.assemblyai.com/v2/transcript"

    # Upload the audio file
    with open(file_path, 'rb') as f:
        response = requests.post(upload_url, headers=headers, files={'file': f})
        upload_response = response.json()

    # Request a transcription and sentiment analysis
    transcript_request = {
        "audio_url": upload_response['upload_url'],
        "sentiment_analysis": True
    }
    response = requests.post(transcript_url, json=transcript_request, headers=headers)
    transcript_response = response.json()

    # Poll for transcription and sentiment analysis completion
    transcript_id = transcript_response['id']
    while True:
        response = requests.get(f"{transcript_url}/{transcript_id}", headers=headers)
        transcript_response = response.json()
        if transcript_response['status'] == 'completed':
            return transcript_response
        elif transcript_response['status'] == 'failed':
            return "Transcription failed."
        st.write("Waiting for transcription and sentiment analysis to complete...")
        time.sleep(5)

# Chunk text to fit within token limits
def chunk_text(text, max_tokens=2000):
    words = text.split()
    chunks = []
    current_chunk = []
    current_length = 0

    for word in words:
        word_length = len(word) + 1  # +1 for the space
        if current_length + word_length > max_tokens:
            chunks.append(' '.join(current_chunk))
            current_chunk = [word]
            current_length = word_length
        else:
            current_chunk.append(word)
            current_length += word_length

    if current_chunk:
        chunks.append(' '.join(current_chunk))

    return chunks

# Generate questions using OpenAI GPT-4
def generate_questions(openai_api_key, prompt="Generate a list of questions for gathering software requirements...", max_tokens=150):
    openai.api_key = openai_api_key
    response = openai.Completion.create(
        engine="gpt-4",
        prompt=prompt,
        max_tokens=max_tokens
    )
    questions = response.choices[0].text.strip().split('\n')
    return questions

# Process each chunk with chaining
def process_chunks(openai_api_key, chunks):
    all_responses = []
    for chunk in chunks:
        response = generate_questions(openai_api_key, prompt=f"Analyze the following transcript and extract key requirements:\n{chunk}")
        all_responses.extend(response)
    return all_responses

# Save transcript and sentiment analysis
def save_transcript_and_sentiment(transcript_data, file_basename):
    transcript_text = transcript_data['text']
    sentiment_analysis = transcript_data['sentiment_analysis_results']

    base_dir = 'p_transcripts'
    sub_dir = os.path.join(base_dir, file_basename)
    ensure_directories(base_dir, sub_dir)

    # Save transcript as .txt file
    transcript_path = os.path.join(sub_dir, f"{file_basename}.txt")
    with open(transcript_path, 'w') as f:
        f.write(transcript_text)

    # Save sentiment analysis as .csv file
    sentiment_path = os.path.join(sub_dir, f"{file_basename}_sentiment.csv")
    sentiment_df = pd.DataFrame(sentiment_analysis)
    sentiment_df.to_csv(sentiment_path, index=False)

# Read PDF
def read_pdf(file):
    pdf = PdfReader(file)
    text = ''
    for page in pdf.pages:
        text += page.extract_text()
    return text

# Read Excel
def read_excel(file):
    xls = pd.ExcelFile(file)
    data = {}
    for sheet_name in xls.sheet_names:
        data[sheet_name] = xls.parse(sheet_name)
    return data

# Read CSV
def read_csv(file):
    return pd.read_csv(file)

# Index data using FAISS
def index_data(data):
    vector_size = 768  # Assuming we're using embeddings of size 768
    index = faiss.IndexFlatL2(vector_size)
    
    vectors = []
    for item in data:
        # Assuming 'item' is a text that needs to be converted to a vector
        vector = embed_text(item)  # Use your embedding function here
        vectors.append(vector)
    
    vectors = np.array(vectors).astype('float32')
    index.add(vectors)
    return index, vectors

# Placeholder function for embedding text (replace with actual embedding code)
def embed_text(text):
    return np.random.rand(768).astype('float32')  # Replace with actual embedding logic

# Streamlit app
st.title("AI-powered Requirements Gathering")

# Input fields for API keys
openai_api_key = st.text_input("OpenAI API Key", type="password")
assemblyai_api_key = st.text_input("Assembly AI API Key", type="password")

if st.button("Start Recording"):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"recordings/recording_{now}.wav"
    record_audio(filename)

    # Transcribe and analyze the audio file
    if assemblyai_api_key:
        transcript_data = transcribe_and_analyze_audio(filename, assemblyai_api_key)
        if isinstance(transcript_data, str):  # Handle failed transcription
            st.write(transcript_data)
        else:
            file_basename = os.path.splitext(os.path.basename(filename))[0]
            save_transcript_and_sentiment(transcript_data, file_basename)

            st.write("Transcription:")
            st.write(transcript_data['text'])

            st.write("Sentiment Analysis Results:")
            st.write(transcript_data['sentiment_analysis_results'])

            # Chunk the transcript if necessary
            chunks = chunk_text(transcript_data['text'])

            # Process each chunk with OpenAI GPT-4
            if openai_api_key:
                responses = process_chunks(openai_api_key, chunks)
                st.write("Generated Requirements:")
                for response in responses:
                    st.write(response)
            else:
                st.write("Please provide OpenAI API Key")
    else:
        st.write("Please provide Assembly AI API Key")

# File uploader for additional data
uploaded_files = st.file_uploader("Upload additional data (PDF, CSV, Excel)", type=["pdf", "csv", "xlsx"], accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        file_basename = os.path.splitext(uploaded_file.name)[0]
        file_extension = os.path.splitext(uploaded_file.name)[1]
        sub_dir = os.path.join('p_transcripts', file_basename)
        ensure_directories('p_transcripts', sub_dir)

        if file_extension == '.pdf':
            text = read_pdf(uploaded_file)
            text_path = os.path.join(sub_dir, f"{file_basename}.txt")
            with open(text_path, 'w') as f:
                f.write(text)
            st.write(f"PDF content saved to {text_path}")

        elif file_extension == '.csv':
            df = read_csv(uploaded_file)
            csv_path = os.path.join(sub_dir, f"{file_basename}.csv")
            df.to_csv(csv_path, index=False)
            st.write(f"CSV content saved to {csv_path}")

        elif file_extension == '.xlsx':
            data = read_excel(uploaded_file)
            for sheet_name, df in data.items():
                excel_path = os.path.join(sub_dir, f"{file_basename}_{sheet_name}.csv")
                df.to_csv(excel_path, index=False)
                st.write(f"Excel sheet {sheet_name} content saved to {excel_path}")

# Best practices analysis (placeholder for your actual logic)
def analyze_best_practices(transcript, data_files):
    # Implement your best practices analysis logic here
    gaps = ["Example gap 1", "Example gap 2"]
    return gaps

# Analyze gaps and best practices
if st.button("Analyze Gaps and Best Practices"):
    transcript_path = os.path.join('p_transcripts', file_basename, f"{file_basename}.txt")
    with open(transcript_path, 'r') as f:
        transcript = f.read()
    
    gaps = analyze_best_practices(transcript, uploaded_files)
    st.write("Identified Gaps:")
    for gap in gaps:
        st.write(gap)
    
    # Save gaps analysis
    gaps_path = os.path.join('p_transcripts', file_basename, f"{file_basename}_gaps.txt")
    with open(gaps_path, 'w') as f:
        for gap in gaps:
            f.write(f"{gap}\n")
    st.write(f"Gaps analysis saved to {gaps_path}")
