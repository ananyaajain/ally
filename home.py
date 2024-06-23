# home_page.py
import streamlit as st

def display_home_page(first_name):
    #st.sidebar.title("Navigation")
    menu = ["Home", "About", "Contact us", "Logout"]
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Home":
        st.subheader(f"Welcome, {first_name}!")
        st.write("This is the home page of the Virtual Co-worker app.")
        # Add more functionality for the home page as needed.

    elif choice == "Logout":
        st.session_state['logged_in'] = False
        st.session_state['username'] = ""
        st.experimental_rerun()
