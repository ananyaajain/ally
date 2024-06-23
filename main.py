import streamlit as st
import openai
import requests
import sounddevice as sd
import numpy as np
import queue
import tempfile
import os
import asyncio
import re
import requests
from scipy.io.wavfile import write
from dotenv import load_dotenv
from hume import HumeVoiceClient, MicrophoneInterface, VoiceSocket

# Load environment variables
load_dotenv()

# Configure OpenAI API
openai_api_key = os.getenv("OPENAI_API_KEY")
openai.api_key = openai_api_key

# Configure Hume API
hume_api_key = os.getenv("HUME_API_KEY")
hume_secret_key = os.getenv("HUME_SECRET_KEY")

evi_config = os.getenv('EVI_CONFIG_ID')

# Configure LMNT API
lmnt_api_key = os.getenv("LMNT_API_KEY")

# Audio recording settings
fs = 44100
duration = 5  # seconds
q = queue.Queue()
message_counter = 0

def audio_callback(indata, frames, time, status):
    q.put(indata.copy())

def record_audio():
    with sd.InputStream(samplerate=fs, channels=1, callback=audio_callback):
        sd.sleep(duration * 1000)

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

    if response.status_code == 200:
        result = response.json()
        # Assuming Hume AI provides text transcription
        transcription = result.get('transcription', 'No transcription available')
        return transcription
    else:
        return ""

def process_nlp(text):
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
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
        st.write("Failed to synthesize speech")

async def user_input_handler(socket: VoiceSocket):
    while True:
        user_input = await asyncio.to_thread(input, "Type a message to send or 'Q' to quit: ")
        if user_input.strip().upper() == "Q":
            print("Closing the connection...")
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
            f"{role}: {content}\n"
        )

        if "models" in message and "prosody" in message["models"]:
            scores = message["models"]["prosody"]["scores"]
            num = 3

    elif msg_type == "tool_call":
        if message["name"] == "meeting_book":
            m_string = message['parameters']
            m = json.loads(m_string)
            summary = m["summary"]
            description = m["description"]
            start_time = m["start_time"]
            end_time = m["end_time"]
            attendees = m["attendees"]
            st.write(end_time)
            meeting_book(summary, description, start_time, end_time, attendees)
        else: 
            m = message["parameters"]
            department_name= extract_dept(m)
            #st.write(f"Extracted Department: {department_name}")

            url = "https://api.airtable.com/v0/app2HEPZ58uPbPtSI/Imported%20table"
            #put department_name instead in params
            params = {'filterByFormula': f"{{Department}}='{department_name}'"}
            headers = {"Authorization": "Bearer pat6OFB1ifiCsbjrV.f89f18d4f03f2d749ec947b46ac2aa8affaf53dd1c2a7645d45a9e77a221c230"}
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 200:
                st.write(response.json())

    # elif msg_type != "audio_output":
    #     for key, value in message.items():
    #         #message_box += f"{key}: {value}\n"

    st.write(message_box)

    # Update Streamlit with the new message
    if "message" in message and "content" in message["message"]:
        st.session_state.transcript += f"{message['message']['role']}: {message['message']['content']}\n"
        st.session_state.messages.append(f"{message['message']['role']}: {message['message']['content']}")

def extract_dept(message):
    department_pattern = re.compile(r'"department"\s*:\s*"([^"]+)"')
    match = department_pattern.search(message)
    if match:
        return match.group(1)
    return "Unknown Department"

def get_top_n_emotions(prosody_inferences, number):
    sorted_inferences = sorted(prosody_inferences.items(), key=lambda item: item[1], reverse=True)
    return sorted_inferences[:number]

def on_error(error):
    print(f"Error: {error}")
    

async def hume_interaction():
    try:
        client = HumeVoiceClient(hume_api_key, hume_secret_key)
        async with client.connect_with_handlers(
            config_id=evi_config,
            on_message=on_message,
            on_error=on_error,
            enable_audio=True,
        ) as socket:
            microphone_task = asyncio.create_task(MicrophoneInterface.start(socket))
            user_input_task = asyncio.create_task(user_input_handler(socket))
            await asyncio.gather(microphone_task, user_input_task)
    except Exception as e:
        print(f"Exception occurred: {e}")

async def display_interaction_page():
    # Initialize Streamlit state
    if 'transcript' not in st.session_state:
        st.session_state.transcript = ""
    if 'messages' not in st.session_state:
        st.session_state.messages = []

    # Main Streamlit App
    st.title("Virtual Co-worker")

    if st.button("Start Interaction"):
        audio_file = record_audio()

        if audio_file:
            # Analyze emotion and transcribe audio
            user_input = analyze_emotion_and_transcribe(audio_file)
            st.write(f"{user_input}")

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

    def display_messages():
        transcript_container.text_area("Transcript", value=st.session_state.transcript, height=400, key="transcript_area")
        messages_container.empty()
        with messages_container:
            for message in st.session_state.messages:
                st.write(message)

    display_messages()

import streamlit as st
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import os

def get_calendar_service():
    if "credentials" not in st.session_state:
        st.session_state.credentials = None

    if st.session_state.credentials and st.session_state.credentials.expired and st.session_state.credentials.refresh_token:
        st.session_state.credentials.refresh(Request())
    elif not st.session_state.credentials:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                    "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                    "redirect_uris": ["http://localhost:8501"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token"
                }
            },
            scopes=['https://www.googleapis.com/auth/calendar']
        )
        flow.redirect_uri = 'http://localhost:8501'

        auth_url, _ = flow.authorization_url(prompt='consent')
        st.write(f"Please go to this URL: [Google Calendar Authorization]({auth_url})")

        code = st.text_input("Enter the authorization code")
        if code:
            flow.fetch_token(code=code)
            st.session_state.credentials = flow.credentials

            # Save credentials for the session
            with open('token.pickle', 'wb') as token:
                pickle.dump(st.session_state.credentials, token)

    if st.session_state.credentials:
        service = build('calendar', 'v3', credentials=st.session_state.credentials)
        return service
    return None

def meeting_book(summary, description, start_time, end_time, attendees=[]):
    service = get_calendar_service()
    if service:
        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_time,
                'timeZone': 'America/Los_Angeles',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'America/Los_Angeles',
            },
            'attendees': [{'email': email} for email in attendees],
        }
        try:
            event = service.events().insert(calendarId='primary', body=event).execute()
            st.write(f"Event created: {event.get('htmlLink')}")
        except Exception as e:
            st.write(f"An error occurred: {e}")
    else:
        st.write("Could not authenticate Google Calendar service.")