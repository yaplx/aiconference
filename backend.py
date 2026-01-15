import fitz  # PyMuPDF
import re
import csv
import io
import os
from openai import OpenAI
from fpdf import FPDF
import prompts  # <--- Imported prompts

# ==============================================================================
# 1. CONFIGURATION & CONSTANTS
# ==============================================================================

HEADER_MAP = {
    "ABSTRACT": "ABSTRACT",
    "INTRODUCTION": "INTRODUCTION",
    "RELATED WORK": "RELATED WORK",
    "LITERATURE REVIEW": "RELATED WORK",
    "BACKGROUND": "RELATED WORK",
    "REFERENCES": "REFERENCES",
    "BIBLIOGRAPHY": "REFERENCES",
    "ACKNOWLEDGMENT": "ACKNOWLEDGMENT",
    "ACKNOWLEDGEMENTS": "ACKNOWLEDGMENT",
    "APPENDIX": "APPENDIX",
    "APPENDICES": "APPENDIX",
    "DECLARATION": "DECLARATION"
}

SKIP_REVIEW_SECTIONS = [
    "ABSTRACT",
    "PREAMBLE",
    "PREAMBLE/INTRODUCTION",
    "REFERENCES",
    "BIBLIOGRAPHY",
    "ACKNOWLEDGMENT",
    "APPENDIX",
    "DECLARATION"
]

IGNORE_CAPTION_KEYWORDS = [
    "FIGURE", "FIG", "FIG.",
    "TABLE", "TAB", "TAB.",
    "IMAGE", "IMG", "IMG.",
    "CHART", "GRAPH", "DIAGRAM",
    "EQ", "EQUATION"
]


# ==============================================================================
# 2. INITIALIZATION
# ==============================================================================
def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


# ==============================================================================
# 3. HELPER FUNCTIONS
# ==============================================================================
def roman_to_int(s):
    roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    s = s.upper()
    total = 0
    prev_value = 0
    try:
        for char in reversed(s):
            if char not in roman_map: return None
            value = roman_map[char]
            if value < prev_value:
                total -= value
            else:
                total += value
            prev_value = value
        return total
    except:
        return None


def _parse_header_components(text):
    pattern = re.compile(r"^([IVXLCDMivxlcdm]+|\d+)(\.?)\s+([A-Z].*)$")
    match = pattern.match(text)
    if match:
        return match.group(1), match.group(3).strip()
    return None, None


def _is_valid_numbered_header(num_str, phrase, expected_number):
    if len(phrase) >= 30: return False

    clean_phrase = phrase.upper().strip()
    for keyword in IGNORE_CAPTION_KEYWORDS:
        if clean_phrase.startswith(keyword):
            return False

    current_val = 0
    if num_str.isdigit():
        current_val = int(num_str)
    else:
        val = roman_to_int(num_str)
        if val is None: return False
        current_val = val
    return current_val == expected_number


def _get_mapped_title(text):
    clean_upper = text.upper().strip().replace(":", "")
    if clean_upper in HEADER_MAP:
        return HEADER_MAP[clean_upper]
    return None


def combine_section_content(sections):
    """
    Helper to join all section content into a single string.
    Used for the First Pass (Desk Reject) prompt.
    """
    full_text = []
    for sec in sections:
        full_text.append(f"--- {sec['title']} ---")
        full_text.append(sec['content'])
    return "\n".join(full_text)


# ==============================================================================
# 4. MAIN SECTIONING LOGIC
# ==============================================================================
def extract_sections_visual(uploaded_file):
    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    all_lines = []
    for page in doc:
        text = page.get_text("text")
        lines = text.split('\n')
        for line in lines:
            clean = line.strip()
            if clean: all_lines.append(clean)
    doc.close()

    sections = []
    current_section = {"title": "Preamble/Introduction", "content": ""}
    expected_number = 1

    i = 0
    while i < len(all_lines):
        line = all_lines[i]
        detected_header = False
        num_str = ""
        phrase = ""
        is_numbered = False

        p_num, p_phrase = _parse_header_components(line)
        if p_num and _is_valid_numbered_header(p_num, p_phrase, expected_number):
            detected_header = True
            is_numbered = True
            num_str = p_num
            phrase = p_phrase
        elif not detected_header and i + 1 < len(all_lines):
            num_match = re.match(r"^([IVXLCDMivxlcdm]+|\d+)(\.?)$", line)
            if num_match:
                potential_num = num_match.group(1)
                next_line = all_lines[i + 1].strip()
                if len(next_line) < 30 and next_line and next_line[0].isupper():
                    if _is_valid_numbered_header(potential_num, next_line, expected_number):
                        detected_header = True
                        is_numbered = True
                        num_str = potential_num
                        phrase = next_line
                        i += 1

        if not detected_header:
            mapped_title = _get_mapped_title(line)
            if mapped_title:
                detected_header = True
                is_numbered = False
                phrase = mapped_title

        if detected_header:
            if current_section["content"].strip():
                sections.append(current_section)
            if is_numbered:
                current_section = {"title": f"{num_str}. {phrase}", "content": ""}
                expected_number += 1
            else:
                current_section = {"title": phrase, "content": ""}
        else:
            current_section["content"] += line + " "
        i += 1

    if current_section["content"].strip():
        sections.append(current_section)
    return sections


# ==============================================================================
# 5. FIRST PASS EVALUATION (GPT-5) - UPDATED TO USE PROMPTS.PY
# ==============================================================================
def evaluate_first_pass(client, paper_title, abstract_text, conference_name):
    # Fetch prompt from prompts.py
    prompt = prompts.get_first_pass_prompt(conference_name, paper_title, abstract_text)

    try:
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"


# ==============================================================================
# 6. SECTION REVIEW (GPT-5) - UPDATED TO USE PROMPTS.PY
# ==============================================================================
def generate_section_review(client, section_name, section_text, paper_title):
    clean_name = section_name.upper().strip()
    clean_name = re.sub(r"^[\d\w]+\.\s*", "", clean_name)

    if clean_name in SKIP_REVIEW_SECTIONS or section_name.upper() in SKIP_REVIEW_SECTIONS:
        return None

    section_focus = ""
    if "METHOD" in clean_name:
        section_focus = "Focus on: Reproducibility, mathematical soundness, and clarity of the algorithm steps."
    elif "RESULT" in clean_name:
        section_focus = "Focus on: Fairness of baselines, statistical significance, and whether claims match the data."
    elif "INTRO" in clean_name:
        section_focus = "Focus on: Clarity of the research gap and explicit contribution statement."
    elif "RELATED" in clean_name:
        section_focus = "Focus on: Coverage of recent state-of-the-art works (post-2020)."
    elif "CONCLUSION" in clean_name:
        section_focus = "Focus on: Whether the conclusion is supported by the experiments presented."

    # Fetch prompt from prompts.py
    prompt = prompts.get_section_review_prompt(paper_title, section_name, section_focus, section_text)

    try:
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"


# ==============================================================================
# 7. PDF GENERATION (EXACTLY AS PROVIDED IN YOUR WORKING VERSION)
# ==============================================================================
def create_pdf_report(full_report_text, filename="document.pdf"):
    full_text_processed = full_report_text

    pdf = FPDF()
    pdf.add_page()

    # --- FONT SETUP ---
    font_family = "Arial"
    font_path = "DejaVuSans.ttf"

    if os.path.exists(font_path):
        try:
            pdf.add_font('DejaVu', '', font_path, uni=True)
            font_family = 'DejaVu'
        except Exception as e:
            print(f"Warning: Could not load DejaVu font: {e}")

    # --- HEADER GENERATION ---

    # 1. Main Title
    pdf.set_font(font_family, '', 16)
    pdf.cell(0, 10, txt="AI-Optimized Reviewer Assistant Report", ln=True, align='C')
    pdf.ln(2)

    # 2. Header Disclaimer (Gray, Small)
    pdf.set_text_color(100, 100, 100)  # Gray
    pdf.set_font(font_family, '', 8)
    header_disclaimer = (
        "DISCLAIMER: This is an automated assistant tool. The 'RECOMMENDATION' is a "
        "suggestion based on structural and content analysis. "
        "The Human Reviewer must verify all 'FOCUS POINTS' manually."
    )
    pdf.multi_cell(0, 4, header_disclaimer, align='C')
    pdf.ln(8)

    # 3. "REPORT FOR" Line (Black, Larger)
    pdf.set_text_color(0, 0, 0)  # Black
    pdf.set_font(font_family, '', 14)
    pdf.cell(0, 10, txt=f"REPORT FOR: {filename}", ln=True, align='L')
    pdf.ln(2)

    # --- BODY CONTENT ---
    pdf.set_font(font_family, '', 11)

    lines = full_text_processed.split('\n')
    for line in lines:
        if font_family == 'DejaVu':
            clean = line.strip()
        else:
            clean = line.strip().encode('latin-1', 'replace').decode('latin-1')

        if "**DECISION:** REJECT" in clean:
            pdf.set_text_color(200, 0, 0)  # Red
            pdf.cell(0, 10, txt=clean, ln=True)
            pdf.set_text_color(0, 0, 0)
        elif "**DECISION:** PROCEED" in clean:
            pdf.set_text_color(0, 150, 0)  # Green
            pdf.cell(0, 10, txt=clean, ln=True)
            pdf.set_text_color(0, 0, 0)
        elif "--- SECTION:" in clean or "SECTION TITLE:" in clean or "IMPORTANT DISCLAIMER" in clean or "SCOPE OF REVIEW" in clean:
            pdf.ln(5)
            pdf.cell(0, 10, txt=clean, ln=True)
        else:
            pdf.multi_cell(0, 5, clean)

    return pdf.output(dest="S").encode("latin-1")


# ==============================================================================
# 8. CSV BATCH GENERATOR
# ==============================================================================
def create_batch_csv(paper_results_list):
    output = io.StringIO()
    writer = csv.