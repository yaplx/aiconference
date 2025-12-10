import fitz  # PyMuPDF
from openai import OpenAI
from fpdf import FPDF


# Initialize the OpenAI Client
def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


def extract_text_from_pdf_stream(uploaded_file):
    """Extracts text directly from the uploaded memory stream."""
    try:
        file_bytes = uploaded_file.read()
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text()
        doc.close()
        return text
    except Exception as e:
        return None


def split_into_sections(text):
    """Splits full text into logical sections based on keywords."""
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


def generate_section_review(client, section_name, section_text):
    """Sends a specific section to the LLM for review."""
    """Sends a specific section to the LLM for review."""

    # --- DYNAMIC INSTRUCTION LOGIC ---
    # Base instructions applicable to ALL sections
    special_focus = ""

    # If this is the RESULTS section, add specific focus on usefulness
    if "result" in section_name.lower():
        special_focus = """
            Since this is the RESULTS section, your PRIMARY focus must be on:
            - Are the results useful and significant?
            - Do they clearly prove the proposed method works?
            - Are the comparisons with baselines fair and convincing?
            """
    # If this is Abstract or Intro, focus more on Novelty/Relevance
    elif "abstract" in section_name.lower() or "introduction" in section_name.lower():
        special_focus = """
            Since this is the Introduction/Abstract, your PRIMARY focus must be on:
            - Is the problem clearly defined and relevant to IEEE conferences?
            - Is the proposed solution novel and interesting compared to existing work?
            """

    # --- FINAL PROMPT ---
    prompt = f"""
        You are a strict IEEE conference reviewer.
        Review the following '{section_name}' section of a submitted paper.

        General Evaluation Criteria for all sections:
        1. Relevance to standard IEEE conference topics.
        2. Novelty and Interest (is this work new?).
        3. Clarity and Scientific Rigor.

        {special_focus}

        Provide 3-5 specific, actionable improvements based on the text below.

        Section Content:
        {section_text[:15000]} 
        """
    try:
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Error querying AI: {str(e)}"


def create_pdf_report(full_report_text):
    """Generates a downloadable PDF report."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Title
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="AI Paper Improvement Report", ln=True, align='C')
    pdf.ln(10)

    # Body
    pdf.set_font("Arial", size=12)

    # Sanitize text to prevent crashes (Latin-1 fix)
    safe_text = full_report_text.encode('latin-1', 'replace').decode('latin-1')

    pdf.multi_cell(0, 10, safe_text)

    return pdf.output(dest="S").encode("latin-1", "replace")