import streamlit as st
import fitz  # PyMuPDF
import os
from openai import OpenAI
from dotenv import load_dotenv

# === 1. SETUP & AUTHENTICATION ===

# Try to load environment variables from a local .env file
load_dotenv()

# Logic to find the API Key safely (Dual Mode: Cloud vs. Local)
api_key = None

if "OPENAI_API_KEY" in st.secrets:
    # Option A: We are running on Streamlit Cloud
    api_key = st.secrets["OPENAI_API_KEY"]
elif os.getenv("OPENAI_API_KEY"):
    # Option B: We are running locally on your laptop
    api_key = os.getenv("OPENAI_API_KEY")

# Stop the app if no key is found
if not api_key:
    st.error("🚨 API Key not found! Please set it in .env (for local) or Streamlit Secrets (for cloud).")
    st.stop()

# Initialize OpenAI Client
client = OpenAI(api_key=api_key)


# === 2. HELPER FUNCTIONS ===

def extract_text_from_pdf_stream(uploaded_file):
    """
    Extracts text directly from the uploaded memory stream.
    No need to save the file to disk first.
    """
    try:
        # Read the file stream as bytes
        file_bytes = uploaded_file.read()
        # Open with PyMuPDF
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
    """
    Splits the full text into logical sections based on keywords.
    """
    sections = {}
    keywords = ["Abstract", "Introduction", "Method", "Results", "Conclusion", "References"]

    # Case-insensitive search
    text_lower = text.lower()

    for i, keyword in enumerate(keywords):
        start = text_lower.find(keyword.lower())
        if start != -1:
            # Determine end index: either the next keyword or end of text
            if i + 1 < len(keywords):
                next_keyword = keywords[i + 1]
                end = text_lower.find(next_keyword.lower(), start)
                if end == -1: end = len(text)
            else:
                end = len(text)

            # Extract the actual text (using original case)
            content = text[start:end].strip()
            sections[keyword] = content

    return sections


def generate_section_review(section_name, section_text):
    """
    Sends a specific section to the LLM for review.
    """
    prompt = f"""
    You are an IEEE conference reviewer assistant. 
    Review the following '{section_name}' section.
    Suggest 3 specific improvements regarding clarity, scientific rigor, or formatting.

    Section Content:
    {section_text[:3000]}  # Truncated to avoid token limits
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # or gpt-3.5-turbo
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Error querying AI: {str(e)}"


# === 3. MAIN USER INTERFACE ===

st.set_page_config(page_title="FYP Paper Reviewer", page_icon="📄")

st.title("📄 AI Conference Paper Reviewer")
st.markdown("""
**Upload your conference paper (PDF)**. 
The AI will split it into sections (Abstract, Intro, etc.) and give specific feedback for each.
""")

# File Uploader
uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")

if uploaded_file is not None:
    # "Analyze" Button
    if st.button("Analyze Paper"):

        with st.spinner("Processing PDF..."):
            # 1. Extract Text
            full_text = extract_text_from_pdf_stream(uploaded_file)

            if not full_text:
                st.error("Could not extract text. Is this a scanned PDF?")
                st.stop()

            # 2. Split Sections
            sections = split_into_sections(full_text)

            # Fallback if splitting fails
            if not sections:
                st.warning("⚠️ Could not detect standard sections. Analyzing full text.")
                sections = {"Full Document": full_text}

        # 3. Analyze & Display Results
        progress_bar = st.progress(0)
        total = len(sections)

        for i, (name, content) in enumerate(sections.items()):
            # Update Progress
            progress_bar.progress((i + 1) / total)

            with st.expander(f"🔍 Review: {name}", expanded=True):
                st.info(f"Analyzing {len(content)} characters...")
                feedback = generate_section_review(name, content)
                st.markdown(feedback)

        st.success("✅ Review Complete!")