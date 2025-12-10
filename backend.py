import fitz  # PyMuPDF
import re
import os
from openai import OpenAI
from fpdf import FPDF


# --- 1. INITIALIZATION ---
def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


# --- 2. TEXT EXTRACTION (Updated to return clean lines) ---
def extract_text_from_pdf_stream(uploaded_file):
    try:
        file_bytes = uploaded_file.read()
        doc = fitz.open(stream=file_bytes, filetype="pdf")

        all_lines = []
        for page in doc:
            # "text" mode is standard; "blocks" can sometimes help but complicates order.
            text = page.get_text("text")

            # Split and clean basic whitespace
            raw_lines = text.split('\n')
            for line in raw_lines:
                clean = line.strip()
                if clean:
                    all_lines.append(clean)

        doc.close()
        return all_lines
    except Exception as e:
        return []

    # --- 3. SMART PARSING LOGIC (Fixed for Split Headers) ---


def _is_standalone_header_number(line):
    """Checks if a line is just a number like '1' or 'IV' or '2.'"""
    # Matches "1", "1.", "IV", "IV."
    return re.match(r"^(\d+|[IVX]+)\.?$", line.strip()) is not None


def _is_potential_title_text(line):
    """Checks if a line looks like a title (mostly uppercase or Title Case)."""
    # Reject long sentences
    if len(line) > 80:
        return False
    # Check for All Caps (common in headers) or Title Case
    # We require at least one uppercase letter to avoid matching "1. a small point"
    return re.search(r"[A-Z]", line) is not None


def _is_level_1_header(line):
    """
    Checks for standard single-line headers.
    Matches: "1. Introduction", "1 Introduction", "IV. Method", "ABSTRACT"
    """
    clean_line = line.strip()
    if len(clean_line) > 100: return False

    # 1. Standard Numbered Pattern (e.g., "1. Introduction", "IV Method")
    # Digits/Roman -> Optional Dot -> Space -> Capital Letter
    numeric_pattern = r"^(\d+|(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3}))\.?\s+[A-Z]"

    # 2. Key Section Names (Fallback for unnumbered Abstract/Intro)
    # We accept these even without numbers
    keywords = ["ABSTRACT", "INTRODUCTION", "RELATED WORK", "METHOD", "EXPERIMENTS", "CONCLUSION"]
    upper_line = clean_line.upper()

    # Strict match for keywords (must be at START of line)
    for kw in keywords:
        # Matches "ABSTRACT" or "1. ABSTRACT" or "I. ABSTRACT"
        if upper_line.startswith(kw) or (len(upper_line.split()) < 4 and kw in upper_line):
            return True

    if re.match(numeric_pattern, clean_line):
        return True

    return False


def split_into_sections(text_lines):
    STOP_KEYWORDS = ["REFERENCES", "BIBLIOGRAPHY", "APPENDIX", "APPENDICES", "ACKNOWLEDGEMENT"]
    sections = {}
    current_header = "PREAMBLE"
    sections[current_header] = []

    i = 0
    while i < len(text_lines):
        line = text_lines[i].strip()

        # --- A. CLEAN NOISE ---
        # If your input literally has "", remove it.
        # This regex removes tags from the start of the line
        line = re.sub(r"^\\s*", "", line)

        if not line:
            i += 1
            continue

        # --- B. CHECK STOP KEYWORDS ---
        upper_line = line.upper().replace('.', '')
        is_stop_word = False
        for keyword in STOP_KEYWORDS:
            if keyword in upper_line and len(upper_line) < len(keyword) + 10:
                is_stop_word = True
                break
        if is_stop_word:
            break

            # --- C. DETECT HEADERS (Split or Single) ---
        is_new_header = False
        header_title = ""

        # Case 1: Split Header (Line i is "1", Line i+1 is "INTRODUCTION")
        if i + 1 < len(text_lines):
            next_line = re.sub(r"^\\s*", "", text_lines[i + 1].strip())

            if _is_standalone_header_number(line) and _is_potential_title_text(next_line):
                header_title = f"{line} {next_line}"  # Merge them
                is_new_header = True
                i += 1  # Skip the next line since we consumed it

        # Case 2: Standard Single Line Header
        if not is_new_header and _is_level_1_header(line):
            header_title = line
            is_new_header = True

        # --- D. SAVE SECTION ---
        if is_new_header:
            current_header = header_title
            sections[current_header] = []
        else:
            sections[current_header].append(line)

        i += 1

    # Remove Preamble
    if "PREAMBLE" in sections:
        del sections["PREAMBLE"]

    final_output = {k: "\n".join(v) for k, v in sections.items() if v}
    return final_output


# --- 4. AI REVIEW GENERATION (With Title) ---
def generate_section_review(client, section_name, section_text, paper_title="Untitled Paper"):
    special_focus = ""
    if "result" in section_name.lower():
        special_focus = "Since this is RESULTS, focus on significance and proof of method."
    elif "intro" in section_name.lower():
        special_focus = "Focus on problem definition and novelty."

    prompt = f"""
        You are a strict IEEE conference reviewer.
        Paper Title: "{paper_title}"
        Current Section: '{section_name}'

        ### FORMATTING RULES
        1. No Markdown (**bold**). 
        2. Use math symbols freely (θ, π).
        3. Professional tone.

        ### OBJECTIVES
        1. Relevance.
        2. Novelty.
        3. Rigor.

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


# --- 5. PDF REPORT (Font Support) ---
def create_pdf_report(full_report_text):
    pdf = FPDF()
    pdf.add_page()

    # Path to font - UPDATE THIS if needed
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
        # Fallback
        pdf.set_font("Arial", size=12)
        safe_text = full_report_text.encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 10, safe_text)
        return pdf.output(dest="S").encode("latin-1", "replace")