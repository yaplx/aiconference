import fitz  # PyMuPDF
import re
from openai import OpenAI
from fpdf import FPDF


# --- 1. INITIALIZATION ---
def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


# --- 2. TEXT EXTRACTION (UPDATED) ---
def extract_text_from_pdf_stream(uploaded_file):
    """
    Extracts text directly from the uploaded memory stream.
    Returns a LIST of lines to support line-by-line parsing.
    """
    try:
        file_bytes = uploaded_file.read()
        doc = fitz.open(stream=file_bytes, filetype="pdf")

        all_lines = []
        for page in doc:
            # "blocks" is often cleaner than "text" for preserving newlines
            text = page.get_text("text")
            # Split into lines immediately
            all_lines.extend(text.split('\n'))

        doc.close()
        return all_lines
    except Exception as e:
        return []  # Return empty list on error


# --- 3. DYNAMIC PARSING LOGIC (NEW) ---
def _is_level_1_header(line):
    """
    Internal Helper: checks if a line is a main header (Level 1).
    Matches: "1. Introduction", "IV. Methodology"
    Ignores: "1.1", "II.A", "I like apples"
    """
    clean_line = line.strip()

    # Safety: Headers are rarely > 100 chars
    if len(clean_line) > 120:
        return False

    # Arabic Pattern: Digit + Dot + SPACE (e.g., "1. ")
    # The space ensures we don't match "1.1" (which has a digit after the dot)
    arabic_pattern = r"^\d+\.\s+.*"

    # Roman Pattern: Roman Numeral + Dot + SPACE (e.g., "IV. ")
    # Matches Roman Numerals followed immediately by a dot and space
    roman_pattern = r"^(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})\.\s+.*"

    if re.match(arabic_pattern, clean_line) or re.match(roman_pattern, clean_line):
        return True
    return False


def split_into_sections(text_lines):
    """
    Dynamically groups text into Main Sections.
    - Captures "1." or "I."
    - Merges "1.1" or "II.A" into the parent section.
    - STOPS at References/Appendix.
    """
    # Keywords that stop the parsing immediately
    STOP_KEYWORDS = ["REFERENCES", "BIBLIOGRAPHY", "APPENDIX", "APPENDICES", "ACKNOWLEDGEMENT"]

    sections = {}
    current_header = "PREAMBLE"  # Default container for Title/Abstract
    sections[current_header] = []

    for line in text_lines:
        clean_line = line.strip()
        if not clean_line:
            continue

        # A. Check Stop Keywords (Case Insensitive)
        upper_line = clean_line.upper().replace('.', '')

        # Check if line contains strict stop keywords
        is_stop_word = False
        for keyword in STOP_KEYWORDS:
            # Matches if the line IS the keyword or starts with it (e.g., "7. REFERENCES")
            if keyword in upper_line and len(upper_line) < len(keyword) + 10:
                is_stop_word = True
                break

        if is_stop_word:
            break  # Stop processing the rest of the file

        # B. Check for New Main Section
        if _is_level_1_header(clean_line):
            current_header = clean_line
            sections[current_header] = []  # Start a new list for this section
        else:
            # C. Add Content
            # Appends regular text OR subsections (1.1, 1.2) to the current main header
            sections[current_header].append(clean_line)

    # Convert lists to single strings
    # Only return sections that actually have content
    final_output = {k: "\n".join(v) for k, v in sections.items() if v}
    return final_output


# --- 4. AI REVIEW GENERATION ---
def generate_section_review(client, section_name, section_text):
    """
    Sends a specific section to the LLM for review.
    """

    # --- DYNAMIC INSTRUCTION LOGIC ---
    # Logic: "intro" matches "1. INTRODUCTION", "result" matches "IV. RESULTS"
    special_focus = ""

    if "result" in section_name.lower():
        special_focus = """
            Since this is the RESULTS section, your PRIMARY focus must be on:
            - Are the results useful and significant?
            - Do they clearly prove the proposed method works?
            - Are the comparisons with baselines fair and convincing?
            """
    elif "abstract" in section_name.lower() or "introduction" in section_name.lower() or "preamble" in section_name.lower():
        special_focus = """
            Since this is the Introduction/Abstract, your PRIMARY focus must be on:
            - Is the problem clearly defined and relevant to IEEE conferences?
            - Is the proposed solution novel and interesting compared to existing work?
            """

    # --- FINAL PROMPT ---
    # I have refined this to be strict as requested
    prompt = f"""
        You are a strict IEEE conference reviewer.
        Review the following '{section_name}' section.

        ### STRICT DATA RULES
        1. **Do not modify the source text.** You are reviewing it, not rewriting it.
        2. **Do not hallucinate** methods or results not present in the text.
        3. **Ignore References/Appendix** if any accidentally slipped in.

        ### REVIEW OBJECTIVES
        1. Relevance to standard IEEE conference topics.
        2. Novelty and Interest (is this work new?).
        3. Clarity and Scientific Rigor.

        {special_focus}

        Provide 3-5 specific, actionable improvements based ONLY on the text below.

        Section Content:
        {section_text[:15000]} 
        """
    try:
        # Note: 'gpt-5' is not generally available yet.
        # Ensure you use 'gpt-4o' or 'gpt-4-turbo' unless you have specific beta access.
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"⚠️ Error querying AI: {str(e)}"


# --- 5. REPORT GENERATION ---
def create_pdf_report(full_report_text):
    """Generates a downloadable PDF report."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    # Title
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="AI Paper Improvement Report", ln=True, align='C')
    pdf.ln(10)

    # Body
    pdf.set_font("Arial", size=12)

    # Sanitize text to prevent crashes (Latin-1 fix)
    # Using 'replace' handles unmapped characters gracefully
    safe_text = full_report_text.encode('latin-1', 'replace').decode('latin-1')

    pdf.multi_cell(0, 10, safe_text)

    return pdf.output(dest="S").encode("latin-1", "replace")