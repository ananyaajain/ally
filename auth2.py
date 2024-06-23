import streamlit as st
import sqlite3
from sqlite3 import Error
from home import display_home_page
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
import requests
import os

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

CLIENT_SECRETS_FILE = os.getenv('CLIENT_SECRETS_FILE', 'client_secrets.json')
SCOPES = ["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid"]
REDIRECT_URI = "http://localhost:8501"

flow = Flow.from_client_secrets_file(
    CLIENT_SECRETS_FILE,
    scopes=SCOPES,
    redirect_uri=REDIRECT_URI
)

# Database functions
def create_connection():
    conn = None
    try:
        conn = sqlite3.connect('users.db')
    except Error as e:
        st.error(f"Error: {e}")
    return conn

def create_table(conn):
    try:
        sql_create_users_table = """CREATE TABLE IF NOT EXISTS users (
                                    id integer PRIMARY KEY,
                                    username text NOT NULL UNIQUE,
                                    password text,
                                    email text NOT NULL UNIQUE
                                );"""
        cursor = conn.cursor()
        cursor.execute(sql_create_users_table)
    except Error as e:
        st.error(f"Error: {e}")

def add_user(conn, user):
    sql = '''INSERT INTO users(username, password, email)
             VALUES(?,?,?)'''
    cur = conn.cursor()
    cur.execute(sql, user)
    conn.commit()

def verify_user(conn, username, password):
    sql = "SELECT * FROM users WHERE username=? AND password=?"
    cur = conn.cursor()
    cur.execute(sql, (username, password))
    rows = cur.fetchall()
    return len(rows) > 0

def verify_google_user(conn, email):
    sql = "SELECT * FROM users WHERE email=?"
    cur = conn.cursor()
    cur.execute(sql, (email,))
    rows = cur.fetchall()
    return len(rows) > 0

# Initialize database
conn = create_connection()
if conn is not None:
    create_table(conn)
else:
    st.error("Error! Cannot create the database connection.")

# Streamlit app
def main():
    st.title("Ally")

    # Session state to track user login status
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['username'] = ""
        st.session_state['email'] = ""                                   

    if st.session_state['logged_in']:
        display_home_page(st.session_state['username'])
    else:
        login_sign_up_page(conn)

def login_sign_up_page(conn):
    menu = ["Login", "Sign Up"]
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Login":
        st.subheader("Login")

        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login"):
            if verify_user(conn, username, password):
                st.session_state['logged_in'] = True
                st.session_state['username'] = username
                st.experimental_rerun()
            else:
                st.error("Invalid username or password. Please try again.")

    elif choice == "Sign Up":
        st.subheader("Create New Account")

        new_user = st.text_input("Username")
        new_password = st.text_input("Password", type="password")
        email = st.text_input("Email")

        if st.button("Sign Up"):
            try:
                add_user(conn, (new_user, new_password, email))
                st.success("You have successfully created an account!")
                st.info("Go to Login Menu to login")
            except sqlite3.IntegrityError:
                st.error("Username already exists. Please choose a different username.")

        # Google Sign Up Button
        auth_url, _ = flow.authorization_url(prompt='consent')
        st.markdown(f'<a href="{auth_url}" target="_self"><button>Sign Up with Google</button></a>', unsafe_allow_html=True)

        # Handle Google OAuth2.0 callback
        if st.get_query_params().get("code"):
            flow.fetch_token(authorization_response=st.get_query_params()["code"])
            credentials = flow.credentials
            request = Request()
            credentials.refresh(request)

            userinfo_endpoint = "https://www.googleapis.com/oauth2/v1/userinfo"
            params = {"alt": "json"}
            headers = {"Authorization": f"Bearer {credentials.token}"}
            response = requests.get(userinfo_endpoint, params=params, headers=headers)
            user_info = response.json()

            if verify_google_user(conn, user_info["email"]):
                st.session_state['logged_in'] = True
                st.session_state['username'] = user_info["name"]
                st.session_state['email'] = user_info["email"]
                st.experimental_rerun()
            else:
                add_user(conn, (user_info["name"], "", user_info["email"]))
                st.session_state['logged_in'] = True
                st.session_state['username'] = user_info["name"]
                st.session_state['email'] = user_info["email"]
                st.experimental_rerun()

if __name__ == "__main__":
    main()
