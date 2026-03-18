import streamlit as st
import os
import backend
from dotenv import load_dotenv
from conference_options import CONFERENCE_OPTIONS

st.set_page_config(page_title="Conference Desk Reviewer", page_icon="⚖️", layout="wide")
load_dotenv()

# --- Auth & API ---
if "results" not in st.session_state: st.session_state.results = None
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
client = backend.get_openai_client(api_key)

# --- UI Header ---
st.title("⚖️ AI Conference Reviewer")
c1, c2 = st.columns(2)
with c1:
    target_conf = st.selectbox("Target Conference Track", CONFERENCE_OPTIONS)
with c2:
    audience_selection = st.radio("Generate Report For:", ["Committee", "Authors"])
    audience = "author" if "Authors" in audience_selection else "reviewer"

uploaded_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True)
show_details = st.checkbox("Show details on screen", value=True)

# --- The "Tidy" Processing Loop ---
if uploaded_files and st.button("🚀 Start AI Review"):
    st.session_state.results = []
    progress_bar = st.progress(0)

    for i, file in enumerate(uploaded_files):
        with st.status(f"Processing {file.name}...") as status:
            # All the complex loops, pods, and logic now live inside this one call:
            res = backend.process_paper_workflow(client, file, target_conf, audience)
            st.session_state.results.append(res)

            progress_bar.progress((i + 1) / len(uploaded_files))
            status.update(label=f"Completed: {file.name}", state="complete")
    st.rerun()

# --- Display Results ---
if st.session_state.results:
    # (Results display code remains here as it is purely visual)
    backend.render_ui_results(st.session_state.results)