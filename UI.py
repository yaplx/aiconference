import streamlit as st
import os
import zipfile
import io
from dotenv import load_dotenv

# Import our custom backend logic
import backend

# === 1. PAGE CONFIG & AUTHENTICATION ===

st.set_page_config(page_title="FYP Paper Reviewer", page_icon="📄")
load_dotenv()

# Initialize Session State variables if they don't exist
if "processing" not in st.session_state:
    st.session_state.processing = False
if "generated_reports" not in st.session_state:
    st.session_state.generated_reports = None


# --- Password Logic ---
def check_password():
    if "APP_PASSWORD" in st.secrets:
        secret_password = st.secrets["APP_PASSWORD"]
    elif os.getenv("APP_PASSWORD"):
        secret_password = os.getenv("APP_PASSWORD")
    else:
        return True

    user_input = st.text_input("🔑 Enter Access Password", type="password")
    if user_input == secret_password:
        return True
    elif user_input == "":
        st.warning("Please enter the password to continue.")
        return False
    else:
        st.error("❌ Incorrect password")
        return False


if not check_password():
    st.stop()

# --- API Key Logic ---
api_key = None
if "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]
elif os.getenv("OPENAI_API_KEY"):
    api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    st.error("🚨 API Key not found! Check .env or Secrets.")
    st.stop()

# Initialize the client
client = backend.get_openai_client(api_key)

# === 2. MAIN USER INTERFACE ===

st.title("📄 AI Conference Paper Reviewer")
st.markdown("Upload **one or more** conference papers (PDF).")

# 1. DISABLE WIDGETS IF PROCESSING
# We use the 'disabled' argument based on our state variable
is_locked = st.session_state.processing

uploaded_files = st.file_uploader(
    "Choose PDF file(s)",
    type="pdf",
    accept_multiple_files=True,
    disabled=is_locked  # <--- Locked if processing
)

# Checkbox is also locked during processing
show_visuals = st.checkbox(
    "Show detailed feedback on screen",
    value=True,
    disabled=is_locked  # <--- Locked if processing
)

# === 3. ANALYSIS LOGIC ===

# If files are uploaded AND we are not currently processing...
if uploaded_files and not st.session_state.processing:
    # Show the button
    if st.button(f"Analyze {len(uploaded_files)} Paper(s)"):
        # LOCK THE UI
        st.session_state.processing = True
        st.session_state.generated_reports = None  # Clear old results
        st.rerun()  # Restart to apply the "disabled" grey-out effect

# IF WE ARE IN PROCESSING MODE (This runs automatically after the rerun)
if st.session_state.processing and uploaded_files:

    main_progress = st.progress(0)
    temp_reports = []

    # Run the Loop
    for file_index, uploaded_file in enumerate(uploaded_files):
        main_progress.progress(file_index / len(uploaded_files))

        st.divider()
        st.subheader(f"📄 Processing: {uploaded_file.name}")

        current_paper_report = f"REPORT FOR: {uploaded_file.name}\n\n"

        # Initialize paper_title with filename as fallback
        paper_title = uploaded_file.name

        with st.spinner(f"Reading {uploaded_file.name}..."):
            # UPDATED: backend now returns a LIST of lines
            text_lines = backend.extract_text_from_pdf_stream(uploaded_file)

            if not text_lines:
                st.error(f"Could not extract text from {uploaded_file.name}.")
                continue

            # --- DETECT TITLE ---
            # Grab the first non-empty line to use as the Title (since we delete Preamble)
            for line in text_lines:
                clean = line.strip()
                if clean:
                    paper_title = clean
                    break

            # UPDATED: Pass the list of lines to the new parser
            sections = backend.split_into_sections(text_lines)

            if not sections:
                st.warning(f"⚠️ No sections detected. Analyzing full text as one block.")
                sections = {"Full Document": "\n".join(text_lines)}

        # Create tabs only if requested
        tabs = None
        if show_visuals:
            section_names = list(sections.keys())
            if len(section_names) > 0:
                tabs = st.tabs(section_names)

        for i, (name, content) in enumerate(sections.items()):
            # --- UPDATED: PASS TITLE TO BACKEND ---
            feedback = backend.generate_section_review(client, name, content, paper_title)

            current_paper_report += f"\n\n--- SECTION: {name} ---\n"
            current_paper_report += feedback

            # Optional Visuals
            if show_visuals and tabs:
                with tabs[i]:
                    st.caption(f"Analyzing {name}...")
                    st.markdown(feedback)
            elif not show_visuals:
                st.write(f"✅ Analyzed section: {name}")

        # Generate PDF
        pdf_bytes = backend.create_pdf_report(current_paper_report)
        original_name = uploaded_file.name.replace(".pdf", "")
        new_filename = f"{original_name}_review.pdf"
        temp_reports.append((new_filename, pdf_bytes))

    main_progress.progress(1.0)
    st.success("✅ All papers processed!")

    # SAVE RESULTS TO STATE & UNLOCK
    st.session_state.generated_reports = temp_reports
    st.session_state.processing = False
    st.rerun()  # Restart to unlock the UI and show download buttons

# === 4. DOWNLOAD SECTION (PERSISTENT) ===
# This part runs even after the app refreshes/unlocks
if st.session_state.generated_reports:
    st.write("---")
    st.subheader("📥 Download Results")

    reports = st.session_state.generated_reports

    if len(reports) == 1:
        single_filename, single_bytes = reports[0]
        st.download_button(
            label=f"Download Report ({single_filename})",
            data=single_bytes,
            file_name=single_filename,
            mime="application/pdf"
        )
    else:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for file_name, file_data in reports:
                zf.writestr(file_name, file_data)

        zip_buffer.seek(0)
        st.download_button(
            label=f"📦 Download All {len(reports)} Reports (ZIP)",
            data=zip_buffer,
            file_name="All_Reviews.zip",
            mime="application/zip"
        )

    # Optional: Button to clear results and start over
    if st.button("Start New Review"):
        st.session_state.generated_reports = None
        st.rerun()