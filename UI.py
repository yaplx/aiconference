import streamlit as st
import os
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
        return True  # No password set, allow entry

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

# Initialize the client using our backend helper
client = backend.get_openai_client(api_key)

# === 2. MAIN USER INTERFACE ===

st.title("📄 AI Conference Paper Reviewer")
st.markdown("Upload your conference paper (PDF) to get specific feedback.")

uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file is not None:
    if st.button("Analyze Paper"):

        full_report_string = ""

        with st.spinner("Processing PDF..."):
            # CALL BACKEND: Extract Text
            full_text = backend.extract_text_from_pdf_stream(uploaded_file)

            if not full_text:
                st.error("Could not extract text. Is this a scanned PDF?")
                st.stop()

            # CALL BACKEND: Split Sections
            sections = backend.split_into_sections(full_text)

            if not sections:
                st.warning("⚠️ No standard sections detected. Analyzing full text.")
                sections = {"Full Document": full_text}

        # Progress Bar Logic
        progress_bar = st.progress(0)
        total = len(sections)

        for i, (name, content) in enumerate(sections.items()):
            progress_bar.progress((i + 1) / total)

            with st.expander(f"🔍 Review: {name}", expanded=True):
                # CALL BACKEND: Generate Review
                feedback = backend.generate_section_review(client, name, content)
                st.markdown(feedback)

                # Append to report string
                full_report_string += f"\n\n--- SECTION: {name} ---\n"
                full_report_string += feedback

        st.success("✅ Review Complete!")

        # Download Section
        st.write("---")
        st.subheader("📥 Download Report")

        # CALL BACKEND: Create PDF
        pdf_bytes = backend.create_pdf_report(full_report_string)

        # Generate Filename
        original_name = uploaded_file.name.replace(".pdf", "")
        new_filename = f"{original_name}_peer_review_report.pdf"

        st.download_button(
            label="Download Report as PDF",
            data=pdf_bytes,
            file_name=new_filename,
            mime="application/pdf"
        )