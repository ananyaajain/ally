import streamlit as st
import openai
import requests
import sounddevice as sd
import numpy as np
import queue
import tempfile
import os
import asyncio
import io
import logging
import re
from scipy.io.wavfile import write
from dotenv import load_dotenv
from hume import HumeVoiceClient, MicrophoneInterface, VoiceSocket, VoiceConfig
# from app import get_calendar_service


load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")
openai.api_key = openai_api_key

hume_api_key = os.getenv("HUME_API_KEY")
hume_secret_key = os.getenv("HUME_SECRET_KEY")

lmnt_api_key = os.getenv("LMNT_API_KEY")

evi_config = os.getenv('EVI_CONFIG_ID')
if not evi_config:
    raise ValueError("EVI_CONFIG_ID is not set. Please check your environment variables.")

logger = logging.getLogger("streamlit_logger")
logger.setLevel(logging.DEBUG)

# Create StringIO stream for capturing logs
log_stream = io.StringIO()
stream_handler = logging.StreamHandler(log_stream)
logger.addHandler(stream_handler)

# Audio recording settings
fs = 44100
duration = 5  # seconds
q = queue.Queue()
message_counter = 0

def audio_callback(indata, frames, time, status):
    q.put(indata.copy())

def record_audio():
    logger.info("Recording...")
    with sd.InputStream(samplerate=fs, channels=1, callback=audio_callback):
        sd.sleep(duration * 1000)
    logger.info("Recording stopped")

    # Retrieve data from queue and save to a temporary file
    audio_data = []
    while not q.empty():
        audio_data.append(q.get())
    audio_data = np.concatenate(audio_data, axis=0)

    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    write(temp_file.name, fs, audio_data)
    return temp_file.name

def analyze_emotion_and_transcribe(audio_file):
    with open(audio_file, 'rb') as f:
        response = requests.post(
            'https://api.hume.ai/v0/batch/analyze',
            headers={'x-api-key': hume_api_key},
            files={'audio': f}
        )
    logger.info(f"Response Status Code: {response.status_code}")
    logger.info(f"Response Text: {response.text}")

    if response.status_code == 200:
        result = response.json()
        logger.info(f"Emotion Analysis: {result.get('emotions', 'No emotion data available')}")

        # Assuming Hume AI provides text transcription
        transcription = result.get('transcription', 'No transcription available')
        return transcription
    else:
        logger.error("Failed to analyze emotion and transcribe")
        return ""

def process_nlp(text):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a virtual colleague of the user."},
            {"role": "user", "content": text}
        ]
    )
    return response.choices[0].message['content'].strip()

def synthesize_and_speak(text):
    response = requests.post(
        'https://api.lmnt.ai/synthesize',
        headers={'Authorization': f'Bearer {lmnt_api_key}'},
        json={'text': text}
    )
    if response.status_code == 200:
        audio_content = response.content
        temp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
        with open(temp_audio.name, 'wb') as f:
            f.write(audio_content)
        os.system(f"mpg321 {temp_audio.name}")
        os.remove(temp_audio.name)
    else:
        logger.error("Failed to synthesize speech")

async def user_input_handler(socket: VoiceSocket):
    while True:
        user_input = await asyncio.to_thread(input, "Type a message to send or 'Q' to quit: ")
        if user_input.strip().upper() == "Q":
            logger.info("Closing the connection...")
            await socket.close()
            break
        else:
            await socket.send_text_input(user_input)

def on_message(message):
    global message_counter
    message_counter += 1
    msg_type = message["type"]

    message_box = ("")

    if msg_type in {"user_message", "assistant_message"}:
        role = message["message"]["role"]
        content = message["message"]["content"]
        message_box += (
            f"{role}\n:"
            f" {content}\n"
        )

        if "models" in message and "prosody" in message["models"]:
            scores = message["models"]["prosody"]["scores"]
            num = 3
            top_emotions = get_top_n_emotions(prosody_inferences=scores, number=num)


    st.markdown(f'<p>{message_box}</p>', unsafe_allow_html=True)

    # Update Streamlit with the new message
    if "message" in message and "content" in message["message"]:
        st.session_state.transcript += f"{message['message']['role']}: {message['message']['content']}\n"
        st.session_state.messages.append(f"{message['message']['role']}: {message['message']['content']}")

def get_top_n_emotions(prosody_inferences, number):
    sorted_inferences = sorted(prosody_inferences.items(), key=lambda item: item[1], reverse=True)
    return sorted_inferences[:number]

def on_error(error):
    logger.error(f"Error: {error}")

async def hume_interaction():
    try:
        client = HumeVoiceClient(hume_api_key, hume_secret_key)

        async with client.connect_with_handlers(
            config_id=evi_config,
            on_message=on_message,
            on_error=on_error,
            enable_audio=True,
        ) as socket:
        # async with client.connect(config_id=evi_config) as socket:
            microphone_task = asyncio.create_task(MicrophoneInterface.start(socket))
            user_input_task = asyncio.create_task(user_input_handler(socket))
            await asyncio.gather(microphone_task, user_input_task)
            # await MicrophoneInterface.start(socket)
    except Exception as e:
        logger.error(f"Exception occurred: {e}")    

async def main():
    # Initialize Streamlit state
    if 'transcript' not in st.session_state:
        st.session_state.transcript = ""
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    # Main Streamlit App
    st.title("Virtual Co-Worker")

    if st.button("Start Interaction"):
        audio_file = record_audio()

        if audio_file:
            # Analyze emotion and transcribe audio
            user_input = analyze_emotion_and_transcribe(audio_file)

            if user_input:
                # Process NLP
                response_text = process_nlp(user_input)
                st.write(f"Virtual Co-worker: {response_text}")

                # Speak the response
                synthesize_and_speak(response_text)

        # Start Hume AI interaction
        st.write("Starting Hume AI interaction...")
        await hume_interaction()

    # Display the transcript and messages
    transcript_container = st.empty()
    messages_container = st.empty()
    log_container = st.empty()

def display_messages():
    
    transcript_container.text_area("Transcript", value=st.session_state.transcript, height=400, key="transcript_area")
    messages_container.empty()
    with messages_container:
        for message in st.session_state.messages:
            st.write(message)
    log_container.text_area("Logs", value=log_stream.getvalue(), height=200, key="log_area")
    display_messages()

# def book_meeting(summary, description, start_time, end_time, attendees=[]):
#     service = get_calendar_service()
#     if service:
#         event = {
#             'summary': summary,
#             'description': description,
#             'start': {
#                 'dateTime': start_time,
#                 'timeZone': 'America/Los_Angeles',
#             },
#             'end': {
#                 'dateTime': end_time,
#                 'timeZone': 'America/Los_Angeles',
#             },
#             'attendees': [{'email': email} for email in attendees],
#         }
#         event = service.events().insert(calendarId='primary', body=event).execute()
#         st.write(f"Event created: {event.get('htmlLink')}")



# Run the Streamlit app with asyncio
if __name__ == "__main__":
    asyncio.run(main())
