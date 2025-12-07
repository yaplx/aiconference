import streamlit as st
import fitz  # PyMuPDF
import os
from openai import OpenAI
from dotenv import load_dotenv

# === 1. SETUP & AUTHENTICATION ===

st.set_page_config(page_title="FYP Paper Reviewer", page_icon="🔒")

# Try to load environment variables from a local .env file
load_dotenv()


# --- PASSWORD PROTECTION START ---
def check_password():
    """Returns `True` if the user had the correct password."""

    # 1. Get the secret password from Streamlit Secrets or Local .env
    if "APP_PASSWORD" in st.secrets:
        secret_password = st.secrets["APP_PASSWORD"]
    elif os.getenv("APP_PASSWORD"):
        secret_password = os.getenv("APP_PASSWORD")
    else:
        # If no password is set in secrets, allow access (or you can set to fail)
        return True

    # 2. Show input box
    user_input = st.text_input("🔑 Enter Access Password", type="password")

    if user_input == secret_password:
        return True
    elif user_input == "":
        st.warning("Please enter the password to continue.")
        return False
    else:
        st.error("❌ Incorrect password")
        return False


# Stop the app here if password is wrong
if not check_password():
    st.stop()
# --- PASSWORD PROTECTION END ---


# Logic to find the API Key safely (Dual Mode: Cloud vs. Local)
api_key = None
if "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]
elif os.getenv("OPENAI_API_KEY"):
    api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    st.error("🚨 API Key not found! Please set it in .env (for local) or Streamlit Secrets (for cloud).")
    st.stop()

client = OpenAI(api_key=api_key)


# === 2. HELPER FUNCTIONS ===

def extract_text_from_pdf_stream(uploaded_file):
    try:
        file_bytes = uploaded_file.read()
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return ""


def split_into_sections(text):
    sections = {}
    keywords = ["Abstract", "Introduction", "Method", "Results", "Conclusion", "References"]
    text_lower = text.lower()
    for i, keyword in enumerate(keywords):
        start = text_lower.find(keyword.lower())
        if start != -1:
            if i + 1 < len(keywords):
                next_keyword = keywords[i + 1]
                end = text_lower.find(next_keyword.lower(), start)
                if end == -1: end = len(text)
            else:
                end = len(text)
            content = text[start:end].strip()
            sections[keyword] = content
    return sections


def generate_section_review(section_name, section_text):
    prompt = f"""
    You are an IEEE conference reviewer assistant. 
    Review the following '{section_name}' section.
    Suggest 3 specific improvements regarding clarity, scientific rigor, or formatting.
    Section Content:
    {section_text[:3000]}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Error querying AI: {str(e)}"


# === 3. MAIN USER INTERFACE ===

st.title("📄 AI Conference Paper Reviewer")
st.markdown("Upload your conference paper (PDF) to get specific feedback.")

uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file is not None:
    if st.button("Analyze Paper"):
        with st.spinner("Processing PDF..."):
            full_text = extract_text_from_pdf_stream(uploaded_file)
            if not full_text:
                st.error("Could not extract text.")
                st.stop()

            sections = split_into_sections(full_text)
            if not sections:
                st.warning("⚠️ Could not detect standard sections. Analyzing full text.")
                sections = {"Full Document": full_text}

        progress_bar = st.progress(0)
        total = len(sections)
        for i, (name, content) in enumerate(sections.items()):
            progress_bar.progress((i + 1) / total)
            with st.expander(f"🔍 Review: {name}", expanded=True):
                feedback = generate_section_review(name, content)
                st.markdown(feedback)

        st.success("✅ Review Complete!")