import fitz  # PyMuPDF
import re
import os
from openai import OpenAI
from fpdf import FPDF


# --- 1. INITIALIZATION ---
def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


# --- 2. HELPER FUNCTIONS ---
def roman_to_int(s):
    """
    Converts Roman numerals (IV, ii, X) to integers.
    Returns None if the string is not a valid Roman numeral.
    """
    roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    s = s.upper()
    total = 0
    prev_value = 0

    try:
        for char in reversed(s):
            if char not in roman_map:
                return None
            value = roman_map[char]
            if value < prev_value:
                total -= value
            else:
                total += value
            prev_value = value
        return total
    except:
        return None


def _check_header_rules(line, expected_number):
    """
    Validates a line against strict user rules:
    1. Regex: Start of line + Number (Arabic/Roman) + Optional Dot + Spaces + Phrase
    2. Phrase: Must start with Capital Letter.
    3. Length: Phrase length (excluding number/dot) must be < 30 chars.
    4. Sequence: The number must match expected_number (Previous + 1).
    """
    # Regex Breakdown:
    # ^                     -> Start of line
    # ([IVXLCDMivxlcdm]+|\d+) -> Group 1: Number (Roman or Arabic)
    # (\.?)                 -> Group 2: Optional Dot
    # \s+                   -> Spaces (1 or more)
    # ([A-Z].*)             -> Group 3: Phrase (Must start with Capital A-Z)
    pattern = re.compile(r"^([IVXLCDMivxlcdm]+|\d+)(\.?)\s+([A-Z].*)$")

    match = pattern.match(line)
    if not match:
        return False, None, None

    num_str = match.group(1)
    phrase = match.group(3).strip()

    # RULE: Length of phrase < 30 chars
    if len(phrase) >= 30:
        return False, None, None

    # Resolve Number Value
    current_val = 0
    if num_str.isdigit():
        current_val = int(num_str)
    else:
        val = roman_to_int(num_str)
        if val is None:
            return False, None, None
        current_val = val

    # RULE: Sequential Check
    # The detected number must match the expected sequence (e.g., if expected is 2, header must be 2)
    if current_val == expected_number:
        return True, num_str, phrase

    return False, None, None


# --- 3. MAIN SECTIONING LOGIC ---
def extract_sections_visual(uploaded_file):
    """
    Extracts text and groups it into sections based on strict sequential numbering rules.
    """
    # 1. Read PDF Text
    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    all_lines = []
    for page in doc:
        text = page.get_text("text")
        raw_lines = text.split('\n')
        for line in raw_lines:
            # Clean leading whitespace but preserve internal spacing for logic
            clean = line.strip()
            if clean:
                all_lines.append(clean)
    doc.close()

    # 2. State Machine for Sectioning
    sections = []
    current_section = {"title": "Preamble/Introduction", "content": ""}

    # We expect the first numbered section to be 1 (or I)
    expected_number = 1

    # Allow common unnumbered headers (optional, but recommended for papers)
    valid_unnumbered = ["ABSTRACT", "REFERENCES", "BIBLIOGRAPHY", "ACKNOWLEDGMENT", "APPENDIX"]

    for line in all_lines:
        is_numbered, num_str, phrase = _check_header_rules(line, expected_number)

        # Check for special unnumbered headers (Case insensitive check)
        is_special = False
        upper_line = line.upper().replace(":", "").strip()
        if upper_line in valid_unnumbered:
            is_special = True
            phrase = line

        if is_numbered:
            # Save previous section
            if current_section["content"].strip():
                sections.append(current_section)

            # Start new Numbered Section
            current_section = {
                "title": f"{num_str}. {phrase}",
                "content": ""
            }
            # Increment expected number (1 -> 2)
            expected_number += 1

        elif is_special:
            # Save previous section
            if current_section["content"].strip():
                sections.append(current_section)

            # Start new Special Section (No number increment)
            current_section = {
                "title": phrase,
                "content": ""
            }

        else:
            # Just regular content
            current_section["content"] += line + " "

    # Append the final section
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

    font_family = "Arial"

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
            # Handle unicode characters safely for FPDF
            safe_text = clean_line.encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 5, safe_text)

    return pdf.output(dest="S").encode("latin-1")