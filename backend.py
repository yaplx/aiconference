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


def _parse_header_components(text):
    """
    Attempts to parse a line into (Number String, Separator, Phrase).
    Returns (num_str, phrase) or (None, None).
    """
    # Regex for "Number + Optional Dot + Space + Phrase"
    # Matches: "1. Introduction" or "IV Results"
    pattern = re.compile(r"^([IVXLCDMivxlcdm]+|\d+)(\.?)\s+([A-Z].*)$")
    match = pattern.match(text)

    if match:
        return match.group(1), match.group(3).strip()
    return None, None


def _is_valid_header(num_str, phrase, expected_number):
    """
    Validates the parsed components against strict rules.
    """
    # RULE 1: Phrase length < 30 chars
    if len(phrase) >= 30:
        return False

    # RULE 2: Resolve Number Value
    current_val = 0
    if num_str.isdigit():
        current_val = int(num_str)
    else:
        val = roman_to_int(num_str)
        if val is None:
            return False
        current_val = val

    # RULE 3: Sequential Check (Must match expected_number)
    if current_val == expected_number:
        return True

    return False


# --- 3. MAIN SECTIONING LOGIC (Updated for Split Lines) ---
def extract_sections_visual(uploaded_file):
    """
    Extracts text and groups sections, handling cases where
    the number and title are on different lines.
    """
    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    # Extract all lines first
    all_lines = []
    for page in doc:
        text = page.get_text("text")
        raw_lines = text.split('\n')
        for line in raw_lines:
            clean = line.strip()
            if clean:
                all_lines.append(clean)
    doc.close()

    sections = []
    current_section = {"title": "Preamble/Introduction", "content": ""}
    expected_number = 1

    valid_unnumbered = ["ABSTRACT", "REFERENCES", "BIBLIOGRAPHY", "ACKNOWLEDGMENT", "APPENDIX"]

    i = 0
    while i < len(all_lines):
        line = all_lines[i]

        # --- LOGIC START ---
        detected_header = False
        num_str = ""
        phrase = ""

        # Case A: Standard Single Line Header ("1. Introduction")
        p_num, p_phrase = _parse_header_components(line)
        if p_num and _is_valid_header(p_num, p_phrase, expected_number):
            detected_header = True
            num_str = p_num
            phrase = p_phrase

        # Case B: Split Line Header (Line i = "1", Line i+1 = "Introduction")
        # Only check if Case A failed
        elif not detected_header and i + 1 < len(all_lines):
            # Check if current line is JUST a number (e.g. "1" or "1.")
            num_match = re.match(r"^([IVXLCDMivxlcdm]+|\d+)(\.?)$", line)

            if num_match:
                potential_num = num_match.group(1)
                next_line = all_lines[i + 1].strip()

                # Check if next line looks like a title (Capitalized, < 30 chars)
                if len(next_line) < 30 and next_line and next_line[0].isupper():
                    if _is_valid_header(potential_num, next_line, expected_number):
                        detected_header = True
                        num_str = potential_num
                        phrase = next_line
                        i += 1  # Skip the next line since we consumed it as the title!

        # --- PROCESSING ---
        is_special = False
        if not detected_header:
            upper_line = line.upper().replace(":", "").strip()
            if upper_line in valid_unnumbered:
                is_special = True
                phrase = line

        if detected_header:
            if current_section["content"].strip():
                sections.append(current_section)

            current_section = {
                "title": f"{num_str}. {phrase}",
                "content": ""
            }
            expected_number += 1

        elif is_special:
            if current_section["content"].strip():
                sections.append(current_section)
            current_section = {
                "title": phrase,
                "content": ""
            }
        else:
            # If we merged a split header, we already incremented i,
            # so we don't add the title to the content.
            # But if it wasn't a header, we add the line.
            current_section["content"] += line + " "

        i += 1  # Move to next line

    if current_section["content"].strip():
        sections.append(current_section)

    return sections


# --- 4. AI REVIEW GENERATION (Unchanged) ---
def generate_section_review(client, section_name, section_text, paper_title="Untitled Paper"):
    context_instruction = ""
    upper_name = section_name.upper()
    if "METHOD" in upper_name:
        context_instruction = "Check for: Reproducibility gaps, missing equations, or vague algorithm steps."