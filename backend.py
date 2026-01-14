import fitz  # PyMuPDF
import re
from openai import OpenAI
from fpdf import FPDF

# --- 1. CONFIGURATION ---
# ONLY keep headers that are distinct and unlikely to be part of a normal sentence.
# Removed: "METHOD", "RESULTS", "DISCUSSION", "CONCLUSION" (Too risky for false positives)
HEADER_MAP = {
    "ABSTRACT": "ABSTRACT",
    "INTRODUCTION": "INTRODUCTION",
    "REFERENCES": "REFERENCES",
    "BIBLIOGRAPHY": "REFERENCES",
    "ACKNOWLEDGMENT": "ACKNOWLEDGMENT",
    "ACKNOWLEDGEMENTS": "ACKNOWLEDGMENT",
    "APPENDIX": "APPENDIX",
    "APPENDICES": "APPENDIX",
    "DECLARATION": "DECLARATION"
}


# --- 2. INITIALIZATION ---
def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


# --- 3. HELPER FUNCTIONS ---
def roman_to_int(s):
    """Converts Roman numerals to integers."""
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
    """
    Parses a line into (Number String, Phrase).
    Matches: "1. Introduction", "IV Results", etc.
    """
    pattern = re.compile(r"^([IVXLCDMivxlcdm]+|\d+)(\.?)\s+([A-Z].*)$")
    match = pattern.match(text)
    if match:
        return match.group(1), match.group(3).strip()
    return None, None


def _is_valid_numbered_header(num_str, phrase, expected_number):
    """
    Validates numbered headers against strict sequential rules.
    """
    # 1. Check Phrase Length (Must be short title)
    if len(phrase) >= 30: return False

    # 2. Check Number Sequence
    current_val = 0
    if num_str.isdigit():
        current_val = int(num_str)
    else:
        val = roman_to_int(num_str)
        if val is None: return False
        current_val = val

    return current_val == expected_number


def _get_mapped_title(text):
    """
    Checks if text matches a strict structural header (Abstract, References, etc.).
    """
    clean_upper = text.upper().strip().replace(":", "")

    # Strict Check: exact match only to avoid "The Abstract says..."
    if clean_upper in HEADER_MAP:
        return HEADER_MAP[clean_upper]

    return None


# --- 4. MAIN SECTIONING LOGIC ---
def extract_sections_visual(uploaded_file):
    """
    Extracts sections using:
    1. Strict Sequential Numbering (1 -> 2 -> 3)
    2. Split-Line Detection (Number on line i, Title on line i+1)
    3. HEADER_MAP for safe/distinct headers (Abstract, Intro, Ref).
    """
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

        # --- CHECK 1: Standard Numbered Header ("1. Introduction") ---
        p_num, p_phrase = _parse_header_components(line)
        if p_num and _is_valid_numbered_header(p_num, p_phrase, expected_number):
            detected_header = True
            is_numbered = True
            num_str = p_num
            phrase = p_phrase

        # --- CHECK 2: Split-Line Header (Line i="1", Line i+1="Introduction") ---
        elif not detected_header and i + 1 < len(all_lines):
            num_match = re.match(r"^([IVXLCDMivxlcdm]+|\d+)(\.?)$", line)
            if num_match:
                potential_num = num_match.group(1)
                next_line = all_lines[i + 1].strip()

                # Check next line: Capitalized, Short, Matches Sequence
                if len(next_line) < 30 and next_line and next_line[0].isupper():
                    if _is_valid_numbered_header(potential_num, next_line, expected_number):
                        detected_header = True
                        is_numbered = True
                        num_str = potential_num
                        phrase = next_line
                        i += 1  # Skip next line as it was consumed

        # --- CHECK 3: Safe Mapped Header (Abstract, References) ---
        mapped_title = None
        if not detected_header:
            mapped_title = _get_mapped_title(line)
            if mapped_title:
                detected_header = True
                is_numbered = False
                phrase = mapped_title  # Use standardized name

        # --- SAVE & ADVANCE ---
        if detected_header:
            # Save previous section
            if current_section["content"].strip():
                sections.append(current_section)

            # Start New Section
            if is_numbered:
                current_section = {
                    "title": f"{num_str}. {phrase}",
                    "content": ""
                }
                expected_number += 1
            else:
                current_section = {
                    "title": phrase,
                    "content": ""
                }
        else:
            # Append content
            current_section["content"] += line + " "

        i += 1

    # Append final section
    if current_section["content"].strip():
        sections.append(current_section)

    return sections


# --- 5. AI REVIEW GENERATION ---
def generate_section_review(client, section_name, section_text, paper_title="Untitled Paper"):
    upper_name = section_name.upper()
    context_instruction = ""

    if "METHOD" in upper_name:
        context_instruction = "Check for: Reproducibility gaps, missing equations, or vague algorithm steps."
    elif "RESULT" in upper_name:
        context_instruction = "Check for: Missing baselines, unclear metrics, or claims not supported by data."
    elif "INTRO" in upper_name:
        context_instruction = "Check for: Clear research gap and contribution statement."

    prompt = f"""
        You are an AI Assistant to a Human Reviewer.
        Paper: "{paper_title}"
        Section: "{section_name}"
        Outcome: [SURE REJECT / ACCEPT WITH SUGGESTIONS]

        {context_instruction}

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


# --- 6. PDF REPORT GENERATION ---
def create_pdf_report(full_report_text):
    pdf = FPDF()
    pdf.add_page()
    font_family = "Arial"

    pdf.set_font(font_family, 'B', 16)
    pdf.cell(0, 10, txt="AI-Optimized Reviewer Assistant Report", ln=True, align='C')
    pdf.ln(3)

    pdf.set_font(font_family, '', 11)
    lines = full_report_text.split('\n')
    for line in lines:
        clean = line.strip().encode('latin-1', 'replace').decode('latin-1')
        if "--- SECTION:" in clean:
            pdf.ln(5)
            pdf.set_font(font_family,