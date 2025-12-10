import fitz  # PyMuPDF
import re
import os
from openai import OpenAI
from fpdf import FPDF


# --- 1. INITIALIZATION ---
def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


# --- 2. TEXT EXTRACTION ---
def extract_text_from_pdf_stream(uploaded_file):
    try:
        file_bytes = uploaded_file.read()
        doc = fitz.open(stream=file_bytes, filetype="pdf")

        all_lines = []
        for page in doc:
            text = page.get_text("text")
            all_lines.extend(text.split('\n'))

        doc.close()
        return all_lines
    except Exception as e:
        return []

    # --- 3. PARSING LOGIC ---


def _is_level_1_header(line):
    clean_line = line.strip()
    if len(clean_line) > 120: return False

    arabic_pattern = r"^\d+\.\s+.*"
    roman_pattern = r"^(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})\.\s+.*"

    if re.match(arabic_pattern, clean_line) or re.match(roman_pattern, clean_line):
        return True
    return False


def split_into_sections(text_lines):
    STOP_KEYWORDS = ["REFERENCES", "BIBLIOGRAPHY", "APPENDIX", "APPENDICES", "ACKNOWLEDGEMENT"]
    sections = {}
    current_header = "PREAMBLE"
    sections[current_header] = []

    for line in text_lines:
        clean_line = line.strip()
        if not clean_line: continue

        upper_line = clean_line.upper().replace('.', '')
        is_stop_word = False
        for keyword in STOP_KEYWORDS:
            if keyword in upper_line and len(upper_line) < len(keyword) + 10:
                is_stop_word = True
                break

        if is_stop_word: break

        if _is_level_1_header(clean_line):
            current_header = clean_line
            sections[current_header] = []
        else:
            sections[current_header].append(clean_line)

    final_output = {k: "\n".join(v) for k, v in sections.items() if v}
    return final_output


# --- 4. AI REVIEW GENERATION (UPDATED) ---
def generate_section_review(client, section_name, section_text):
    """
    Sends a section to the LLM.
    Now allows Mathematical symbols because we are using a Unicode font.
    """

    special_focus = ""
    if "result" in section_name.lower():
        special_focus = """
        Since this is the RESULTS section, focus on:
        - Are the results significant?
        - Do they prove the proposed method works?
        """
    elif "abstract" in section_name.lower() or "introduction" in section_name.lower():
        special_focus = """
        Since this is the Introduction/Abstract, focus on:
        - Is the problem defined clearly?
        - Is the solution novel?
        """

    # --- REMOVED THE "NO SPECIAL CHARS" RESTRICTION ---
    prompt = f"""
        You are a strict IEEE conference reviewer.
        Review the following '{section_name}' section.

        ### FORMATTING RULES
        1. **Do NOT use Markdown.** (No **bold**, *italics*, or # headers).
        2. **Use mathematical symbols FREELY.** (e.g., use θ, π, →, ≤).
        3. **Keep the tone professional and direct.**

        ### REVIEW OBJECTIVES
        1. Relevance to standard IEEE conference topics.
        2. Novelty and Interest.
        3. Clarity and Scientific Rigor.

        {special_focus}

        Provide 3-5 specific, actionable improvements based ONLY on the text below.

        Section Content:
        {section_text[:15000]} 
        """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error querying AI: {str(e)}"


# --- 5. REPORT GENERATION (FONT FIXED) ---

def create_pdf_report(full_report_text):
    """Generates a downloadable PDF report with Unicode support."""
    pdf = FPDF()
    pdf.add_page()

    # --- UPDATE PATH HERE ---
    # Double check if your file is named "DejaVuSans.ttf" or "dejavu.ttf" inside that folder
    font_path = os.path.join("dejavu-sans-ttf-2.37", "ttf", "DejaVuSans.ttf")

    if os.path.exists(font_path):
        # Register the font
        pdf.add_font('DejaVu', '', font_path, uni=True)
        pdf.set_font('DejaVu', '', 12)

        # Title
        pdf.set_font('DejaVu', '', 16)
        pdf.cell(200, 10, txt="AI Paper Improvement Report", ln=True, align='C')
        pdf.ln(10)

        # Body
        pdf.set_font('DejaVu', '', 12)
        pdf.multi_cell(0, 10, full_report_text)

        return pdf.output(dest="S").encode("latin-1")

    else:
        print(f"❌ ERROR: Font not found at: {font_path}")

        # Fallback to Arial (No symbols)
        pdf.set_font("Arial", size=12)
        safe_text = full_report_text.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 10, safe_text)

        return pdf.output(dest="S").encode("latin-1", "replace")