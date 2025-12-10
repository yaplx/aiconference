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
            raw_lines = text.split('\n')
            for line in raw_lines:
                clean = re.sub(r"^\\s*", "", line.strip())
                if clean:
                    all_lines.append(clean)

        doc.close()
        return all_lines
    except Exception as e:
        return []

    # --- 3. HYBRID PARSING LOGIC ---

def _is_level_1_numbering(line):
    # Matches "1. Title" or "IV. Title", ignores "1.1"
    arabic = r"^\d+\.\s+[A-Z]"
    roman = r"^(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})\.\s+[A-Z]"
    if re.match(arabic, line) or re.match(roman, line):
        return True
    return False


def split_into_sections(text_lines):
    HEADER_MAP = {
        "ABSTRACT": "ABSTRACT",
        "INTRODUCTION": "INTRODUCTION",
        "RELATED WORK": "RELATED WORK",
        "LITERATURE REVIEW": "RELATED WORK",
        "BACKGROUND": "RELATED WORK",
        "METHOD": "METHODOLOGY",
        "METHODS": "METHODOLOGY",
        "METHODOLOGY": "METHODOLOGY",
        "PROPOSED METHOD": "METHODOLOGY",
        "APPROACH": "METHODOLOGY",
        "EXPERIMENT": "EXPERIMENTS",
        "EXPERIMENTS": "EXPERIMENTS",
        "EVALUATION": "EXPERIMENTS",
        "RESULT": "RESULTS",
        "RESULTS": "RESULTS",
        "DISCUSSION": "DISCUSSION",
        "CONCLUSION": "CONCLUSION",
        "CONCLUSIONS": "CONCLUSION",
        "FUTURE WORK": "CONCLUSION"
    }
    STOP_KEYWORDS = ["REFERENCES", "BIBLIOGRAPHY", "APPENDIX", "APPENDICES", "ACKNOWLEDGEMENT"]

    sections = {}
    current_header = "PREAMBLE"
    sections[current_header] = []

    for line in text_lines:
        clean_line = line.strip()
        upper_line = clean_line.upper()

        clean_upper_no_num = re.sub(r"^[\d\.IVXivx]+\s+", "", upper_line).strip()

        is_stop = False
        for stop_word in STOP_KEYWORDS:
            if clean_upper_no_num.startswith(stop_word):
                is_stop = True
                break
        if is_stop: break

        is_new_header = False
        final_header_name = ""

        # Method 1: Keyword Match
        if clean_upper_no_num in HEADER_MAP:
            final_header_name = HEADER_MAP[clean_upper_no_num]
            is_new_header = True
        # Method 2: Numbering Match
        elif _is_level_1_numbering(clean_line):
            final_header_name = clean_line
            is_new_header = True

        if is_new_header:
            current_header = final_header_name
            if current_header not in sections:
                sections[current_header] = []
        else:
            sections[current_header].append(clean_line)

    if "PREAMBLE" in sections:
        del sections["PREAMBLE"]

    final_output = {k: "\n".join(v) for k, v in sections.items() if v}
    return final_output


# --- 4. AI REVIEW GENERATION ---
def generate_section_review(client, section_name, section_text, paper_title="Untitled Paper"):
    special_focus = ""
    if "METHOD" in section_name.upper():
        special_focus = "Focus on: technical depth, clarity, and reproducibility."
    elif "RESULT" in section_name.upper():
        special_focus = "Focus on: Are results significant? Do they prove the method works?"
    elif "INTRO" in section_name.upper():
        special_focus = "Focus on: Is the problem clearly defined? Is the novelty explicitly stated?"

    prompt = f"""
        You are a strict IEEE conference reviewer.
        Paper Title: "{paper_title}"
        Current Section: '{section_name}'

        ### FORMATTING RULES
        1. Plain Text only (no Markdown).
        2. Use Math symbols freely (θ, π, ->).
        3. Professional tone.
        4. Do not modify any data.

        ### OBJECTIVES
        1. Relevance.
        2. Novelty.
        3. Scientific Rigor.

        {special_focus}
        Provide 3-5 actionable improvements based ONLY on the text below.

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
        return f"Error querying AI: {str(e)}"


# --- 5. PDF REPORT GENERATION (UPDATED WITH DISCLAIMER) ---
def create_pdf_report(full_report_text):
    pdf = FPDF()
    pdf.add_page()

    # Path setup
    font_path = os.path.join("dejavu-sans-ttf-2.37", "ttf", "DejaVuSans.ttf")

    # Default fallback font
    font_family = "Arial"

    if os.path.exists(font_path):
        pdf.add_font('DejaVu', '', font_path, uni=True)
        font_family = 'DejaVu'

    # --- TITLE ---
    pdf.set_font(font_family, '', 16)
    pdf.cell(0, 10, txt="AI Paper Improvement Report", ln=True, align='C')
    pdf.ln(3)

    # --- DISCLAIMER SECTION (Updated) ---
    pdf.set_font(font_family, '', 8)  # Smaller font for disclaimer
    pdf.set_text_color(100, 100, 100)  # Grey color

    disclaimer_text = (
        "DISCLAIMER: This automated report relies on header recognition. "
        "1) If a section header is unique or not recognized, that section's content "
        "is automatically merged into the previous section for review. "
        "2) SCOPE: To ensure focused feedback, this tool EXCLUDES the Title page info "
        "(Preamble), References, Bibliography, Acknowledgements, and Appendices."
    )

    # multi_cell wraps text automatically
    pdf.multi_cell(0, 4, txt=disclaimer_text, align='C')
    pdf.ln(10)  # Add space after disclaimer

    # --- MAIN CONTENT ---
    pdf.set_text_color(0, 0, 0)  # Reset to Black
    pdf.set_font(font_family, '', 12)

    if font_family == 'DejaVu':
        pdf.multi_cell(0, 10, full_report_text)
        return pdf.output(dest="S").encode("latin-1")
    else:
        # Fallback cleaning for Arial
        safe_text = full_report_text.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 10, safe_text)
        return pdf.output(dest="S").encode("latin-1", "replace")