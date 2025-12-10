import re


def is_level_1_header(line):
    """
    Returns True if the line matches a Level 1 Header (e.g., "1. Intro", "IV. Method").
    Returns False for subsections (e.g., "1.1", "II.A") or regular text.
    """
    clean_line = line.strip()

    # 1. Safety Check: Skip super long lines (headers are usually short)
    if len(clean_line) > 120:
        return False

    # 2. Arabic Pattern: "1. Title"
    # Matches digit(s) + dot + SPACE.
    # The space \s ensures we don't match "1.1" (which has a digit after the dot).
    arabic_pattern = r"^\d+\.\s+.*"

    # 3. Roman Pattern: "I. Title", "IV. Title"
    # Matches Roman Numerals + dot + SPACE.
    roman_pattern = r"^(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})\.\s+.*"

    # Check matches
    if re.match(arabic_pattern, clean_line) or re.match(roman_pattern, clean_line):
        return True

    return False


def parse_pdf_text(text_lines):
    """
    Parses a list of text strings into sections based on dynamic headers.
    Stops at References/Appendix.
    """

    # Keywords that stop the parsing immediately
    STOP_KEYWORDS = [
        "REFERENCES",
        "BIBLIOGRAPHY",
        "APPENDIX",
        "APPENDICES",
        "ACKNOWLEDGEMENT",
        "ACKNOWLEDGEMENTS"
    ]

    sections = {}
    current_section_title = "PREAMBLE"  # Content before the first real header (Abstract, Title)
    sections[current_section_title] = []

    for line in text_lines:
        clean_line = line.strip()
        if not clean_line:
            continue  # Skip empty lines

        # --- CHECK EXCLUSIONS ---
        # Normalize to uppercase and remove dots to match "REFERENCES" or "7. REFERENCES"
        upper_line = clean_line.upper().replace('.', '')

        # If the line contains a stop keyword and is short (header-like), STOP.
        is_excluded = False
        for keyword in STOP_KEYWORDS:
            if keyword in upper_line and len(upper_line) < len(keyword) + 10:
                is_excluded = True
                break

        if is_excluded:
            break  # Stop processing the rest of the file

        # --- CHECK HEADER ---
        if is_level_1_header(clean_line):
            # New Section Found
            current_section_title = clean_line
            sections[current_section_title] = []
        else:
            # Content or Subsection -> Add to current section
            sections[current_section_title].append(clean_line)

    # --- FORMAT OUTPUT ---
    # Convert lists to strings
    final_output = {k: "\n".join(v) for k, v in sections.items() if v}
    return final_output