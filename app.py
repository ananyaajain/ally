import streamlit as st
import pickle
import os
import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# OAuth2 client configuration from environment variables
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
SCOPES = ['https://www.googleapis.com/auth/calendar']

# Function to get the OAuth2 flow
def get_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uris": ["http://localhost:8501"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token"
            }
        },
        scopes=SCOPES
    )

# Function to authenticate and create the API client
def get_calendar_service():
    if "credentials" not in st.session_state:
        st.session_state.credentials = None

    if st.session_state.credentials and st.session_state.credentials.expired and st.session_state.credentials.refresh_token:
        st.session_state.credentials.refresh(Request())
    elif not st.session_state.credentials:
        flow = get_flow()
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

# Streamlit app
def main():
    st.title("Google Calendar Integration")

    # Login and authenticate with Google Calendar
    service = get_calendar_service()

    if service:
        st.write("Google Calendar authenticated successfully!")

        # Display upcoming events
        if st.button("Show Upcoming Events"):
            now = datetime.datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
            events_result = service.events().list(calendarId='primary', timeMin=now,
                                                  maxResults=10, singleEvents=True,
                                                  orderBy='startTime').execute()
            events = events_result.get('items', [])

            if not events:
                st.write('No upcoming events found.')
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                st.write(f"{start} - {event['summary']}")

        # Form to add new events
        st.subheader("Add New Event")
        event_summary = st.text_input("Event Summary")
        event_start = st.date_input("Event Start Date", datetime.date.today())
        event_end = st.date_input("Event End Date", datetime.date.today())

        if st.button("Add Event"):
            event = {
                'summary': event_summary,
                'start': {
                    'dateTime': event_start.isoformat() + 'T09:00:00-07:00',
                    'timeZone': 'America/Los_Angeles',
                },
                'end': {
                    'dateTime': event_end.isoformat() + 'T17:00:00-07:00',
                    'timeZone': 'America/Los_Angeles',
                },
            }

            event = service.events().insert(calendarId='primary', body=event).execute()
            st.write('Event created: %s' % (event.get('htmlLink')))

def book_meeting(summary, description, start_time, end_time, attendees=[]):
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
        event = service.events().insert(calendarId='primary', body=event).execute()
        st.write(f"Event created: {event.get('htmlLink')}")

if __name__ == "__main__":
    main()
