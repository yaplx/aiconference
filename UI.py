import streamlit as st
import os
import zipfile
import io
from dotenv import load_dotenv
import backend

# ... (Keep your Page Config & Auth exactly as is) ...
st.set_page_config(page_title="Conference Desk Reviewer", page_icon="⚖️", layout="wide")
load_dotenv()

if "processing" not in st.session_state: st.session_state.processing = False
if "results" not in st.session_state: st.session_state.results = None

# ... (Keep check_password and API key check) ...
# [Copy check_password and API key sections from your existing code]
# For brevity, I am showing the critical Logic update below

if not "OPENAI_API_KEY" in st.secrets and not os.getenv("OPENAI_API_KEY"):
    st.error("Missing API Key");
    st.stop()
client = backend.get_openai_client(os.getenv("OPENAI_API_KEY") or st.secrets["OPENAI_API_KEY"])

# ... (UI Layout: Title, Selectbox, Uploader, Checkbox, Button) ...
st.title("⚖️ AI Conference Reviewer")
# [... Your existing UI code for inputs ...]
uploaded_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True)
show_details = st.checkbox("Show details", value=True)

if uploaded_files and st.button("🚀 Start AI Review"):
    st.session_state.processing = True
    st.session_state.results = []
    st.rerun()

# ==========================================
# PROCESSING LOGIC (FIXED)
# ==========================================
if st.session_state.processing and uploaded_files:
    progress_bar = st.progress(0)
    temp_results = []

    for i, uploaded_file in enumerate(uploaded_files):
        try:
            # [Expander and Tab logic as before...]
            if show_details:
                file_container = st.expander(f"📄 Processing: {uploaded_file.name}", expanded=True)
            else:
                file_container = st.empty()

            saved_tabs_data = []
            first_pass_content = ""

            with file_container:
                uploaded_file.seek(0)
                sections = backend.extract_sections_visual(uploaded_file)
                full_text_clean = backend.combine_section_content(sections)
                valid_sections = [s for s in sections if
                                  not any(skip in s['title'].upper() for skip in backend.SKIP_REVIEW_SECTIONS)]

                # ... (Tab creation and Loop logic from previous solution) ...
                # ... (This part was correct in your code) ...

                # Perform First Pass
                first_pass_content = backend.evaluate_first_pass(client, uploaded_file.name, full_text_clean[:4000],
                                                                 "Standard")

                report_log = f"Report: {uploaded_file.name}\n\n{first_pass_content}\n"
                decision = "PROCEED"
                notes = "Notes"

                # Perform Section Review Loop
                for sec in valid_sections:
                    feedback = backend.generate_section_review(client, sec['title'], sec['content'], uploaded_file.name)
                    if feedback:
                        saved_tabs_data.append({"title": sec['title'], "content": feedback})
                        report_log += f"\n--- {sec['title']} ---\n{feedback}"

            # Generate PDF
            pdf_bytes = backend.create_pdf_report(report_log, filename=uploaded_file.name)

            # SAVE RESULT
            temp_results.append({
                'filename': uploaded_file.name,
                'decision': decision,
                'notes': notes,
                'report_text': report_log,
                'pdf_bytes': pdf_bytes,
                'first_pass_content': first_pass_content,
                'saved_tabs_data': saved_tabs_data
            })

        except Exception as e:
            st.error(f"Error: {e}")

        progress_bar.progress((i + 1) / len(uploaded_files))

    # CRITICAL FIX: Ensure we have results before finishing
    if temp_results:
        st.session_state.results = temp_results
    else:
        st.error("Processing failed. No results generated.")

    st.session_state.processing = False
    st.rerun()

# ==========================================
# RESULTS DISPLAY (FIXED)
# ==========================================
if st.session_state.results:
    st.header("📥 Reviews Completed")
    for res in st.session_state.results:
        with st.expander(f"✅ {res['filename']}", expanded=True):
            st.download_button("⬇️ Download PDF", res['pdf_bytes'], file_name=f"{res['filename']}_Report.pdf")

            # REBUILD TABS
            saved = res.get('saved_tabs_data', [])
            if saved:
                titles = ["First Pass"] + [s['title'] for s in saved]
                tabs = st.tabs(titles)
                with tabs[0]:
                    st.write(res.get('first_pass_content', ''))
                for i, s in enumerate(saved):
                    with tabs[i + 1]: st.write(s['content'])

    if st.button("Start New Review"):
        st.session_state.results = None
        st.rerun()