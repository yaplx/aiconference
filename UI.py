import streamlit as st
import os
import backend
import headers_map as hm
from dotenv import load_dotenv
from conference_options import CONFERENCE_OPTIONS

# --- Setup ---
st.set_page_config(page_title="Conference Desk Reviewer", page_icon="⚖️", layout="wide")
load_dotenv()


# --- Auth ---
def check_password():
    secret = st.secrets.get("APP_PASSWORD") or os.getenv("APP_PASSWORD")
    if not secret: return True
    return st.text_input("🔑 Password", type="password") == secret


if not check_password(): st.stop()

# --- Sidebar/Header Layout ---
st.title("⚖️ AI Conference Reviewer")
c1, c2 = st.columns(2)
with c1:
    selected_option = st.selectbox("Track", CONFERENCE_OPTIONS, disabled=st.session_state.get('processing'))
    target_conf = selected_option  # Simplified for brevity
with c2:
    audience_selection = st.radio("Report For:", ["Committee", "Authors"], disabled=st.session_state.get('processing'))
    audience = "author" if "Authors" in audience_selection else "reviewer"

uploaded_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True)
show_details = st.checkbox("Show details on screen", value=True)

# --- The Processing Loop (Clean Version) ---
if uploaded_files and st.button("🚀 Start AI Review"):
    st.session_state.results = []
    progress_bar = st.progress(0)

    for i, file in enumerate(uploaded_files):
        with st.status(f"Processing {file.name}...") as status:
            # We move the complexity to a single backend function
            result = backend.process_single_paper(file, target_conf, audience, show_details)
            st.session_state.results.append(result)
            progress_bar.progress((i + 1) / len(uploaded_files))
            status.update(label=f"Done: {file.name}", state="complete")
    st.rerun()

# --- Results Display (Keeps your exact look) ---
if st.session_state.get('results'):
# ... (Your existing Results & Downloads UI code goes here) ...
# This part is already clean because it's mostly visual!