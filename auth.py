import streamlit as st
import sqlite3
from sqlite3 import Error
from main import display_interaction_page
import asyncio

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
                                    password text NOT NULL,
                                    email text NOT NULL
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

    if st.session_state['logged_in']:
        asyncio.run(display_interaction_page())
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


if __name__ == "__main__":
    main()

