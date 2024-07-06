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
def record_audio(filename, duration=10, fs=44100, device=None):
    try:
        st.write(f"Recording for {duration} seconds...")
        myrecording = sd.rec(int(duration * fs), samplerate=fs, channels=2, device=device)
        sd.wait()  # Wait until recording is finished
        wavio.write(filename, myrecording, fs, sampwidth=2)
        st.write(f"Recording saved as {filename}")
        return True
    except Exception as e:
        st.error(f"Error recording audio: {e}")
        return False

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
def index_data(data, openai_api_key):
    vector_size = 768  # Assuming we're using embeddings of size 768
    index = faiss.IndexFlatL2(vector_size)
    
    vectors = []
    for item in data:
        # Assuming 'item' is a text that needs to be converted to a vector
        vector = embed_text(item, openai_api_key)  # Use your embedding function here
        vectors.append(vector)
    
    vectors = np.array(vectors).astype('float32')
    index.add(vectors)
    return index, vectors

# Function for embedding text using OpenAI
def embed_text(text, openai_api_key):
    openai.api_key = openai_api_key
    response = openai.Embedding.create(
        input=text,
        model="text-embedding-ada-002"  # Example embedding model, adjust as needed
    )
    embeddings = response['data'][0]['embedding']
    return np.array(embeddings).astype('float32')

# Streamlit app
st.title("AI-powered Requirements Gathering")

# Initialize session state for API keys
if 'openai_api_key' not in st.session_state:
    st.session_state.openai_api_key = ''
if 'assemblyai_api_key' not in st.session_state:
    st.session_state.assemblyai_api_key = ''

# Input fields for API keys
st.session_state.openai_api_key = st.text_input("OpenAI API Key", type="password", value=st.session_state.openai_api_key)
st.session_state.assemblyai_api_key = st.text_input("Assembly AI API Key", type="password", value=st.session_state.assemblyai_api_key)

if st.button("Start Recording"):
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"recordings/recording_{now}.wav"
    # You may need to specify the correct audio input device index here
    device_index = 1  # Replace with a valid device index from the output of sd.query_devices()
    if not record_audio(filename, device=device_index):
        st.write("Please upload a compatible audio file below.")

# File uploader for audio files (in case recording fails)
uploaded_audio = st.file_uploader("Upload a compatible audio file (WAV format)", type=["wav" ,"mpeg", "mp3"])

if uploaded_audio is not None:
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"recordings/uploaded_{now}.wav"
    with open(filename, "wb") as f:
        f.write(uploaded_audio.getbuffer())
    st.write(f"Uploaded file saved as {filename}")

    # Transcribe and analyze the uploaded audio file
    if st.session_state.assemblyai_api_key:
        transcript_data = transcribe_and_analyze_audio(filename, st.session_state.assemblyai_api_key)
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
            if st.session_state.openai_api_key:
                responses = process_chunks(st.session_state.openai_api_key, chunks)
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
def analyze_best_practices(transcript, data_files, openai_api_key):
    # Embed transcript and data files
    data_texts = [transcript]
    for file in data_files:
        if file.type == "application/pdf":
            data_texts.append(read_pdf(file))
        elif file.type == "text/csv":
            df = read_csv(file)
            data_texts.append(df.to_string())
        elif file.type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            data = read_excel(file)
            for sheet_name, df in data.items():
                data_texts.append(df.to_string())
    
    # Embed all texts and create FAISS index
    index, vectors = index_data(data_texts, openai_api_key)
    
    # Implement your best practices analysis logic here
    gaps = ["Example gap 1", "Example gap 2"]
    return gaps

# Analyze gaps and best practices
if st.button("Analyze Gaps and Best Practices"):
    transcript_path = os.path.join('p_transcripts', file_basename, f"{file_basename}.txt")
    with open(transcript_path, 'r') as f:
        transcript = f.read()
    
    gaps = analyze_best_practices(transcript, uploaded_files, st.session_state.openai_api_key)
    st.write("Identified Gaps:")
    for gap in gaps:
        st.write(gap)
    
    # Save gaps analysis
    gaps_path = os.path.join('p_transcripts', file_basename, f"{file_basename}_gaps.txt")
    with open(gaps_path, 'w') as f:
        for gap in gaps:
            f.write(f"{gap}\n")
    st.write(f"Gaps analysis saved to {gaps_path}")
