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

uploaded_files = st.file_uploader("Choose PDF file(s)", type="pdf", accept_multiple_files=True)

if uploaded_files:

    # CHANGE 1: Checkbox to Toggle Comments
    show_visuals = st.checkbox("Show detailed feedback on screen", value=True)

    if st.button(f"Analyze {len(uploaded_files)} Paper(s)"):

        main_progress = st.progress(0)
        generated_reports = []

        for file_index, uploaded_file in enumerate(uploaded_files):

            # Update Progress
            main_progress.progress(file_index / len(uploaded_files))

            st.divider()
            st.subheader(f"📄 Processing: {uploaded_file.name}")

            current_paper_report = f"REPORT FOR: {uploaded_file.name}\n\n"

            with st.spinner(f"Reading {uploaded_file.name}..."):
                full_text = backend.extract_text_from_pdf_stream(uploaded_file)
                if not full_text:
                    st.error(f"Could not extract text from {uploaded_file.name}.")
                    continue

                sections = backend.split_into_sections(full_text)
                if not sections:
                    st.warning(f"⚠️ No sections detected. Analyzing full text.")
                    sections = {"Full Document": full_text}

            # CHANGE 2: Only create tabs if the user wants to see them
            tabs = None
            if show_visuals:
                section_names = list(sections.keys())
                tabs = st.tabs(section_names)

            # Analyze Sections
            for i, (name, content) in enumerate(sections.items()):

                # Logic (Always runs to create the PDF)
                feedback = backend.generate_section_review(client, name, content)

                # Add to report string (Always runs)
                current_paper_report += f"\n\n--- SECTION: {name} ---\n"
                current_paper_report += feedback

                # CHANGE 3: Only display on screen if checkbox is checked
                if show_visuals and tabs:
                    with tabs[i]:
                        st.caption(f"Analyzing {name}...")
                        st.markdown(feedback)
                else:
                    # Minimal feedback if visuals are off
                    st.write(f"✅ Analyzed section: {name}")

            # Generate PDF Bytes
            pdf_bytes = backend.create_pdf_report(current_paper_report)

            original_name = uploaded_file.name.replace(".pdf", "")
            new_filename = f"{original_name}_review.pdf"

            generated_reports.append((new_filename, pdf_bytes))

        main_progress.progress(1.0)
        st.success("✅ All papers processed!")

        # === DOWNLOAD LOGIC ===
        if generated_reports:
            st.write("---")
            st.subheader("📥 Download Results")

            if len(generated_reports) == 1:
                single_filename, single_bytes = generated_reports[0]
                st.download_button(
                    label=f"Download Report ({single_filename})",
                    data=single_bytes,
                    file_name=single_filename,
                    mime="application/pdf"
                )
            else:
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for file_name, file_data in generated_reports:
                        zf.writestr(file_name, file_data)

                zip_buffer.seek(0)

                st.download_button(
                    label=f"📦 Download All {len(generated_reports)} Reports (ZIP)",
                    data=zip_buffer,
                    file_name="All_Reviews.zip",
                    mime="application/zip"
                )