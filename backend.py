import fitz  # PyMuPDF
import re
import csv
import io
from openai import OpenAI
from fpdf import FPDF

# --- 1. CONFIGURATION ---
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


# --- 2. INITIALIZATION ---
def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


# --- 3. HELPER FUNCTIONS ---
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


# --- 4. MAIN SECTIONING LOGIC ---
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


# --- 5. FIRST PASS EVALUATION ---
def evaluate_first_pass(client, paper_title, abstract_text, conference_name):
    prompt = f"""
    You are a Senior Area Chair for: "{conference_name}".
    Paper: "{paper_title}"
    Abstract: "{abstract_text[:4000]}"

    Task: Desk Reject Check.

    Criteria for REJECT:
    1. Irrelevant to {conference_name}.
    2. Zero novelty (textbook summary).
    3. Fatal structure (no method/result).

    OUTPUT FORMAT:
    Option 1:
    **DECISION:** REJECT
    **REASON:** (One sentence summary)

    Option 2:
    **DECISION:** PROCEED
    **REASON:** (One sentence summary)
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {str(e)}"


# --- 6. SECTION REVIEW ---
def generate_section_review(client, section_name, section_text, paper_title):
    clean_name = section_name.upper().strip()
    clean_name = re.sub(r"^[\d\w]+\.\s*", "", clean_name)

    if clean_name in SKIP_REVIEW_SECTIONS or section_name.upper() in SKIP_REVIEW_SECTIONS:
        return None

    prompt = f"""
    You are a Technical Reviewer.
    Paper: "{paper_title}"
    Section: "{section_name}"

    Task: Flag issues needing human check.

    OUTPUT FORMAT:
    **STATUS:** [ACCEPT / ACCEPT WITH SUGGESTIONS]

    **FLAGGED ISSUES (If any):**
    - (Point 1...)
    (Leave empty if ACCEPT)

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
        return f"Error: {str(e)}"


# --- 7. PDF GENERATION ---
def create_pdf_report(full_report_text):
    pdf = FPDF()
    pdf.add_page()
    font_family = "Arial"
    pdf.set_font(font_family, 'B', 16)
    pdf.cell(0, 10, txt="AI Reviewer Report", ln=True, align='C')
    pdf.ln(3)
    pdf.set_font(font_family, '', 11)

    lines = full_report_text.split('\n')
    for line in lines:
        clean = line.strip().encode('latin-1', 'replace').decode('latin-1')
        if "**DECISION:** REJECT" in clean:
            pdf.set_text_color(200, 0, 0)
            pdf.set_font(font_family, 'B', 12)
            pdf.cell(0, 10, txt=clean, ln=True)
            pdf.set_text_color(0, 0, 0)
        elif "**DECISION:** PROCEED" in clean:
            pdf.set_text_color(0, 150, 0)
            pdf.set_font(font_family, 'B', 12)
            pdf.cell(0, 10, txt=clean, ln=True)
            pdf.set_text_color(0, 0, 0)
        elif "--- SECTION:" in clean:
            pdf.ln(5)
            pdf.set_font(font_family, 'B', 12)
            pdf.cell(0, 10, txt=clean, ln=True)
            pdf.set_font(font_family, '', 11)
        else:
            pdf.multi_cell(0, 5, clean)
    return pdf.output(dest="S").encode("latin-1")


# --- 8. CSV BATCH GENERATOR (Updated) ---
def create_batch_csv(paper_results_list):
    """
    Generates a simple CSV with 3 columns:
    Filename | Status (Accept/Reject/Accept with Suggestion) | Notes
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(["Filename", "Decision", "Comments"])

    # Rows
    for p in paper_results_list:
        writer.writerow([p['filename'], p['decision'], p['notes']])

    return output.getvalue()