import streamlit as st
import os
import zipfile
import io
from dotenv import load_dotenv
import backend

# === 1. PAGE CONFIG & AUTHENTICATION ===
st.set_page_config(page_title="Conference Desk Reviewer", page_icon="⚖️")
load_dotenv()

if "processing" not in st.session_state: st.session_state.processing = False
if "generated_reports" not in st.session_state: st.session_state.generated_reports = None
if "csv_string" not in st.session_state: st.session_state.csv_string = None
if "structure_debug" not in st.session_state: st.session_state.structure_debug = None

def check_password():
    if "APP_PASSWORD" in st.secrets: secret_password = st.secrets["APP_PASSWORD"]
    elif os.getenv("APP_PASSWORD"): secret_password = os.getenv("APP_PASSWORD")
    else: return True
    user_input = st.text_input("🔑 Enter