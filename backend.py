import fitz  # PyMuPDF
import re
import csv
import io
import os
from openai import OpenAI
from fpdf import FPDF
import prompts  # Imports your local prompts.py file

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
HEADER_MAP = {
    "ABSTRACT": "ABSTRACT", "INTRODUCTION": "INTRODUCTION",
    "RELATED WORK": "RELATED WORK", "LITERATURE REVIEW": "RELATED WORK",
    "BACKGROUND": "RELATED WORK", "REFERENCES": "REFERENCES",
    "BIBLIOGRAPHY": "REFERENCES", "ACKNOWLEDGMENT": "ACKNOWLEDGMENT",
    "ACKNOWLEDGEMENTS": "ACKNOWLEDGMENT", "APPENDIX": "APPENDIX",
    "APPENDICES": "APPENDIX", "DECLARATION": "DECLARATION"
}
SKIP_REVIEW_SECTIONS = [
    "ABSTRACT", "PREAMBLE", "PREAMBLE/INTRODUCTION", "REFERENCES",
    "BIBLIOGRAPHY", "ACKNOWLEDGMENT", "APPENDIX", "DECLARATION"
]
IGNORE_CAPTION_KEYWORDS = [
    "FIGURE", "FIG", "FIG.", "TABLE", "TAB", "TAB.",
    "IMAGE", "IMG", "IMG.", "CHART", "GRAPH", "DIAGRAM", "EQ", "EQUATION"
]


def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


# ==============================================================================
# 2. HELPER FUNCTIONS
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
    if match: return match.group(1), match.group(3).strip()
    return None, None


def _is_valid_numbered_header(num_str, phrase, expected_number):
    if len(phrase) >= 30: return False
    clean_phrase = phrase.upper().strip()
    for keyword in IGNORE_CAPTION_KEYWORDS:
        if clean_phrase.startswith(keyword): return False
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
    if clean_upper in HEADER_MAP: return HEADER_MAP[clean_upper]
    return None


def combine_section_content(sections):
    full_text = []
    for sec in sections:
        full_text.append(f"--- {sec['title']} ---")
        full_text.append(sec['content'])
    return "\n".join(full_text)


def sanitize_text_for_pdf(text):
    # Basic cleanup for common issues
    replacements = {
        u'\u2018': "'", u'\u2019': "'", u'\u201c': '"', u'\u201d': '"',
        u'\u2013': '-', u'\u2014': '-', u'\u2212': '-', "**": ""
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


# ==============================================================================
# 3. EXTRACTION
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
        num_str, phrase, is_numbered = "", "", False

        p_num, p_phrase = _parse_header_components(line)
        if p_num and _is_valid_numbered_header(p_num, p_phrase, expected_number):
            detected_header = True;
            is_numbered = True
            num_str = p_num;
            phrase = p_phrase
        elif not detected_header and i + 1 < len(all_lines):
            num_match = re.match(r"^([IVXLCDMivxlcdm]+|\d+)(\.?)$", line)
            if num_match:
                potential_num = num_match.group(1)
                next_line = all_lines[i + 1].strip()
                if len(next_line) < 30 and next_line and next_line[0].isupper():
                    if _is_valid_numbered_header(potential_num, next_line, expected_number):
                        detected_header = True;
                        is_numbered = True
                        num_str = potential_num;
                        phrase = next_line
                        i += 1

        if not detected_header:
            mapped_title = _get_mapped_title(line)
            if mapped_title:
                detected_header = True;
                is_numbered = False;
                phrase = mapped_title

        if detected_header:
            if current_section["content"].strip(): sections.append(current_section)
            if is_numbered:
                current_section = {"title": f"{num_str}. {phrase}", "content": ""}
                expected_number += 1
            else:
                current_section = {"title": phrase, "content": ""}
        else:
            current_section["content"] += line + " "
        i += 1
    if current_section["content"].strip(): sections.append(current_section)
    return sections


# ==============================================================================
# 4. REVIEW LOGIC (USING PROMPTS.PY & GPT-5)
# ==============================================================================
def evaluate_first_pass(client, paper_title, abstract_text, conference_name):
    # Load prompt from external file
    prompt = prompts.get_first_pass_prompt(conference_name, paper_title, abstract_text)
    try:
        response = client.chat.completions.create(
            model="gpt-5",  # Using gpt-5 as requested
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"


def generate_section_review(client, section_name, section_text, paper_title):
    clean_name = section_name.upper().strip()
    clean_name = re.sub(r"^[\d\w]+\.\s*", "", clean_name)
    if clean_name in SKIP_REVIEW_SECTIONS or section_name.upper() in SKIP_REVIEW_SECTIONS:
        return None

    section_focus = ""
    if "METHOD" in clean_name:
        section_focus = "Focus on: Reproducibility, mathematical soundness."
    elif "RESULT" in clean_name:
        section_focus = "Focus on: Fairness, statistical significance."
    elif "INTRO" in clean_name:
        section_focus = "Focus on: Clarity of research gap."
    elif "RELATED" in clean_name:
        section_focus = "Focus on: Coverage of recent works."
    elif "CONCLUSION" in clean_name:
        section_focus = "Focus on: Whether conclusion is supported."

    # Load prompt from external file
    prompt = prompts.get_section_review_prompt(paper_title, section_name, section_focus, section_text)
    try:
        response = client.chat.completions.create(
            model="gpt-5",  # Using gpt-5 as requested
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"


# ==============================================================================
# 5. PDF GENERATION (ROBUST ENCODING FIX)
# ==============================================================================
def create_pdf_report(full_report_text, filename="document.pdf"):
    full_text_processed = sanitize_text_for_pdf(full_report_text)
    pdf = FPDF()

    # --- FONT LOADING ---
    base_dir = os.path.dirname(os.path.abspath(__file__))
    font_path_1 = os.path.join(base_dir, "dejavu-sans-ttf-2.37", "ttf", "DejaVuSans.ttf")
    font_path_2 = os.path.join(base_dir, "DejaVuSans.ttf")

    font_family = "Arial"
    unicode_font_loaded = False

    # Try loading Unicode font
    try:
        if os.path.exists(font_path_1):
            pdf.add_font('DejaVu', '', font_path_1, uni=True)
            font_family = 'DejaVu'
            unicode_font_loaded = True
        elif os.path.exists(font_path_2):
            pdf.add_font('DejaVu', '', font_path_2, uni=True)
            font_family = 'DejaVu'
            unicode_font_loaded = True
    except:
        pass  # Fallback to Arial if load fails

    # Add Page must happen AFTER font registration
    pdf.add_page()

    # Header
    pdf.set_font(font_family, '', 16)
    pdf.cell(0, 10, txt="AI-Optimized Reviewer Assistant Report", ln=True, align='C')
    pdf.ln(2)
    pdf.set_font(font_family, '', 11)

    lines = full_text_processed.split('\n')
    for line in lines:
        clean = line.strip()

        # SAFETY CHECK: If we are using Arial (non-unicode), we must remove special chars
        # or the PDF generation will crash.
        if not unicode_font_loaded:
            # Replace unknown characters with '?' instead of crashing
            clean = clean.encode('latin-1', 'replace').decode('latin-1')

        if "DECISION:" in clean or "--- SECTION:" in clean:
            pdf.ln(5)
            pdf.cell(0, 10, txt=clean, ln=True)
        else:
            pdf.multi_cell(0, 5, clean)

    # RETURN BYTES SAFELY
    # This prevents the "Error Generating Report" dummy file.
    # It attempts to encode to latin-1, replacing any stubborn characters that fit neither font.
    return pdf.output(dest="S").encode("latin-1", "replace")


def create_batch_csv(paper_results_list):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Filename", "Decision", "Comments"])
    for p in paper_results_list:
        writer.writerow([p['filename'], p['decision'], p['notes']])
    return output.getvalue()