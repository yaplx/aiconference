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
                # Remove tags if they exist
                clean = re.sub(r"^\\s*", "", line.strip())
                if clean:
                    all_lines.append(clean)

        doc.close()
        return all_lines
    except Exception as e:
        return []

    # --- 3. HYBRID PARSING LOGIC (Keywords + Numbers) ---


def _is_level_1_numbering(line):
    """
    Checks if line matches "1. Title" or "IV. Title".
    Strictly ignores subsections like "1.1" or "IV.A".
    """
    # Arabic Pattern: Start -> Digits -> Dot -> Space -> Capital Letter
    # Rejects "1.1" because after the dot is another digit, not space.
    arabic = r"^\d+\.\s+[A-Z]"

    # Roman Pattern: Start -> Roman -> Dot -> Space -> Capital Letter
    roman = r"^(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})\.\s+[A-Z]"

    if re.match(arabic, line) or re.match(roman, line):
        return True
    return False


def split_into_sections(text_lines):
    # 1. Standard Keywords Map
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

        # --- A. CHECK STOP KEYWORDS ---
        # Strip numbers to check strictly for "REFERENCES"
        clean_upper_no_num = re.sub(r"^[\d\.IVXivx]+\s+", "", upper_line).strip()

        is_stop = False
        for stop_word in STOP_KEYWORDS:
            if clean_upper_no_num.startswith(stop_word):
                is_stop = True
                break
        if is_stop: break

        # --- B. DETECTION LOGIC ---
        is_new_header = False
        final_header_name = ""

        # Method 1: Keyword Match (Strongest)
        # We use the version STRIPPED of numbers to match "Introduction"
        if clean_upper_no_num in HEADER_MAP:
            final_header_name = HEADER_MAP[clean_upper_no_num]
            is_new_header = True

        # Method 2: Numbering Match (Fallback for unique headers)
        # Only check this if Method 1 failed.
        # We check the ORIGINAL line for "3. My Custom Algo"
        elif _is_level_1_numbering(clean_line):
            # We use the full line as the title (e.g., "3. PROPOSED FRAMEWORK")
            final_header_name = clean_line
            is_new_header = True

        # --- C. SAVE SECTION ---
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
    # Add focus for Methodology since custom headers usually fall here
    if "METHOD" in section_name.upper() or "PROPOSED" in section_name.upper():
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
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error querying AI: {str(e)}"


# --- 5. PDF REPORT GENERATION ---
def create_pdf_report(full_report_text):
    pdf = FPDF()
    pdf.add_page()

    # UPDATE PATH IF NEEDED
    font_path = os.path.join("dejavu-sans-ttf-2.37", "ttf", "DejaVuSans.ttf")

    if os.path.exists(font_path):
        pdf.add_font('DejaVu', '', font_path, uni=True)
        pdf.set_font('DejaVu', '', 12)
        pdf.set_font('DejaVu', '', 16)
        pdf.cell(200, 10, txt="AI Paper Improvement Report", ln=True, align='C')
        pdf.ln(10)
        pdf.set_font('DejaVu', '', 12)
        pdf.multi_cell(0, 10, full_report_text)
        return pdf.output(dest="S").encode("latin-1")
    else:
        pdf.set_font("Arial", size=12)
        safe_text = full_report_text.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 10, safe_text)
        return pdf.output(dest="S").encode("latin-1", "replace")