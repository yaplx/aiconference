import fitz  # PyMuPDF
import re
import os
from openai import OpenAI
from fpdf import FPDF


# --- 1. INITIALIZATION ---
def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


# --- 2. HELPERS FOR LOGIC ---
def roman_to_int(s):
    """
    Converts Roman numerals (IV, ii, X) to integers.
    Returns None if invalid.
    """
    roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    s = s.upper()
    total = 0
    prev_value = 0

    try:
        for char in reversed(s):
            value = roman_map[char]
            if value < prev_value:
                total -= value
            else:
                total += value
            prev_value = value
        return total
    except KeyError:
        return None


def _is_header_candidate(line, expected_number):
    """
    Checks if a line matches the user's strict rules:
    1. Regex: Number (Arabic/Roman) + Opt Dot + Space + Phrase
    2. Phrase Length < 25 chars
    3. Phrase starts with Capital
    4. Sequence: Number must == expected_number
    """
    # Regex:
    # Group 1: Number (Digits or Roman)
    # Group 2: Optional Dot
    # Group 3: Phrase (Must start with A-Z)
    pattern = re.compile(r"^([IVXLCDMivxlcdm]+|\d+)(\.?)\s+([A-Z].*)$")

    match = pattern.match(line)
    if not match:
        return False, None, None

    num_str = match.group(1)
    phrase = match.group(3)

    # RULE: Phrase length (excluding number) < 25 chars
    if len(phrase) >= 25:
        return False, None, None

    # Resolve Number (Arabic or Roman)
    current_val = 0
    if num_str.isdigit():
        current_val = int(num_str)
    else:
        val = roman_to_int(num_str)
        if val is None:
            return False, None, None
        current_val = val

    # RULE: Strict Sequence (Must match expected number)
    if current_val == expected_number:
        return True, num_str, phrase

    return False, None, None


# --- 3. MAIN PARSING LOGIC ---
def extract_sections_strict(uploaded_file):
    """
    Extracts text and splits it into sections based on strict numbering rules.
    """
    # Read PDF content
    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    all_lines = []
    for page in doc:
        text = page.get_text("text")
        raw_lines = text.split('\n')
        for line in raw_lines:
            clean = re.sub(r"^\s*", "", line.strip())
            if clean:
                all_lines.append(clean)
    doc.close()

    # Sectioning State Machine
    sections = []
    current_section = {"title": "Preamble (Unnumbered)", "content": ""}

    expected_number = 1  # We expect the first valid header to be 1 or I

    # Specific Unnumbered Headers allowed (Exceptions to the rule)
    valid_unnumbered = ["ABSTRACT", "REFERENCES", "BIBLIOGRAPHY", "ACKNOWLEDGMENT"]

    for line in all_lines:
        is_header, num_str, phrase = _is_header_candidate(line, expected_number)

        # Check for allowed unnumbered headers (Abstract, etc.)
        is_special_header = False
        upper_line = line.upper().replace(":", "").strip()
        if upper_line in valid_unnumbered:
            is_special_header = True
            phrase = line  # Use original casing

        if is_header:
            # SAVE PREVIOUS SECTION
            if current_section["content"].strip():
                sections.append(current_section)

            # START NEW NUMBERED SECTION
            current_section = {
                "title": f"{num_str}. {phrase}",
                "content": ""
            }
            expected_number += 1  # Increment expectation (1 -> 2)

        elif is_special_header:
            # SAVE PREVIOUS
            if current_section["content"].strip():
                sections.append(current_section)

            # START NEW SPECIAL SECTION
            current_section = {
                "title": phrase,
                "content": ""
            }
            # We do NOT increment expected_number for unnumbered sections

        else:
            # APPEND CONTENT
            current_section["content"] += line + " "

    # Append final section
    if current_section["content"].strip():
        sections.append(current_section)

    return sections


# --- 4. AI REVIEW GENERATION ---
def generate_section_review(client, section_name, section_text, paper_title="Untitled Paper"):
    context_instruction = ""
    upper_name = section_name.upper()

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

        Your job is to screen this section and provide a clear recommendation.
        You must choose ONE of these two outcomes:
        1. SURE REJECT (Use if there are fatal flaws, missing data, or complete lack of rigor).
        2. ACCEPT WITH SUGGESTIONS (Use if valid but needs improvement).

        ### OUTPUT FORMAT (Strictly follow this):

        **RECOMMENDATION:** [SURE REJECT / ACCEPT WITH SUGGESTIONS]

        **REVIEWER FOCUS POINTS:**
        - (List 2-3 specific lines or claims the human reviewer needs to verify manually).
        - (e.g., "Check equation 3 for derivation errors", "Verify if baseline X is actually comparable").

        **REASONING & IMPROVEMENTS:**
        - (Explain why you chose the recommendation).
        - (If Accept: List improvements).
        - (If Reject: List critical fatal flaws).

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


# --- 5. PDF REPORT GENERATION ---
def create_pdf_report(full_report_text):
    pdf = FPDF()
    pdf.add_page()

    font_family = "Arial"  # Standard fallback

    # --- TITLE ---
    pdf.set_font(font_family, 'B', 16)
    pdf.cell(0, 10, txt="AI-Optimized Reviewer Assistant Report", ln=True, align='C')
    pdf.ln(3)

    # --- DISCLAIMER ---
    pdf.set_font(font_family, '', 8)
    pdf.set_text_color(100, 100, 100)
    disclaimer_text = (
        "DISCLAIMER: This is an automated assistant tool. "
        "The Human Reviewer must verify all 'FOCUS POINTS' manually."
    )
    pdf.multi_cell(0, 4, txt=disclaimer_text, align='C')
    pdf.ln(10)

    # --- MAIN CONTENT ---
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(font_family, '', 11)

    lines = full_report_text.split('\n')
    for line in lines:
        clean_line = line.strip()

        # Simple formatting logic
        if "--- SECTION:" in clean_line:
            pdf.ln(5)
            pdf.set_font(font_family, 'B', 12)
            pdf.cell(0, 10, txt=clean_line, ln=True)
            pdf.set_font(font_family, '', 11)

        elif "**RECOMMENDATION:**" in clean_line:
            pdf.set_font(font_family, 'B', 11)
            pdf.cell(0, 8, txt=clean_line.replace("**", ""), ln=True)
            pdf.set_font(font_family, '', 11)

        else:
            safe_text = clean_line.encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 5, safe_text)

    return pdf.output(dest="S").encode("latin-1")