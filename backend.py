import fitz  # PyMuPDF
import re
import csv
import io
import os
from openai import OpenAI
from fpdf import FPDF
import prompts  #

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
    """
    Sanitizes text to prevent unicode crashes in standard Arial font.
    """
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
    try:
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
    except Exception as e:
        return [{"title": "Error Reading PDF", "content": f"Could not extract text: {e}"}]


# ==============================================================================
# 4. REVIEW LOGIC
# ==============================================================================
def evaluate_first_pass(client, paper_title, abstract_text, conference_name):
    try:
        prompt = prompts.get_first_pass_prompt(conference_name, paper_title, abstract_text)
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        try:
            print(f"GPT-5 Failed ({e}), trying GPT-4o")
            prompt = prompts.get_first_pass_prompt(conference_name, paper_title, abstract_text)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        except Exception as e2:
            return f"AI Error: {str(e2)}"


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

    try:
        prompt = prompts.get_section_review_prompt(paper_title, section_name, section_focus, section_text)
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        try:
            prompt = prompts.get_section_review_prompt(paper_title, section_name, section_focus, section_text)
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        except Exception as e2:
            return f"AI Error: {str(e2)}"


# ==============================================================================
# 5. PDF GENERATION (ROBUST "SEARCH & RESCUE" MODE)
# ==============================================================================
def create_pdf_report(full_report_text, filename="document.pdf"):
    """
    Generates PDF with robust font finding.
    If font load fails, falls back to Arial SILENTLY.
    If PDF generation fails, falls back to Error PDF SILENTLY.
    """
    try:
        pdf = FPDF()
        pdf.add_page()

        font_family = "Arial"
        unicode_font_loaded = False

        # --- ROBUST FONT SEARCH ---
        # We search relative to CWD and Script location
        base_dir = os.path.dirname(os.path.abspath(__file__))
        cwd = os.getcwd()

        possible_paths = [
            # 1. User requested path (relative)
            os.path.join(cwd, "dejavu-sans-ttf-2.37", "ttf", "DejaVuSans.ttf"),
            # 2. Lowercase variation (common issue)
            os.path.join(cwd, "dejavu-sans-ttf-2.37", "ttf", "dejavusans.ttf"),
            # 3. Relative to script location
            os.path.join(base_dir, "dejavu-sans-ttf-2.37", "ttf", "DejaVuSans.ttf"),
            # 4. Direct subfolder
            os.path.join(cwd, "ttf", "DejaVuSans.ttf"),
            # 5. Root
            os.path.join(cwd, "DejaVuSans.ttf")
        ]

        found_font_path = None
        for p in possible_paths:
            if os.path.exists(p):
                found_font_path = p
                break

        if found_font_path:
            try:
                # Attempt to load. If this specific line fails, we catch it locally
                pdf.add_font('DejaVu', '', found_font_path, uni=True)
                font_family = 'DejaVu'
                unicode_font_loaded = True
            except Exception as font_e:
                print(f"Font found at {found_font_path} but failed to load: {font_e}")
                # Continue with Arial

        # --- HEADER ---
        pdf.set_font(font_family, '', 16)
        pdf.cell(0, 10, txt="AI Paper Improvement Report", ln=True, align='C')
        pdf.ln(3)

        # --- DISCLAIMER ---
        pdf.set_font(font_family, '', 8)
        pdf.set_text_color(100, 100, 100)

        disclaimer_text = (
            "DISCLAIMER: This is an automated assistant tool. The 'RECOMMENDATION' is a "
            "suggestion based on structural and content analysis."
        )
        pdf.multi_cell(0, 4, txt=disclaimer_text, align='C')
        pdf.ln(10)

        # --- METADATA ---
        pdf.set_text_color(0, 0, 0)
        pdf.set_font(font_family, '', 14)
        pdf.cell(0, 10, txt=f"REPORT FOR: {filename}", ln=True, align='L')
        pdf.ln(2)

        # --- BODY ---
        pdf.set_font(font_family, '', 12)

        # Sanitize text
        clean_text = sanitize_text_for_pdf(full_report_text)

        lines = clean_text.split('\n')
        for line in lines:
            safe_line = line.strip()

            # CRITICAL: If no unicode font, strip special chars to prevent crash
            if not unicode_font_loaded:
                safe_line = safe_line.encode('latin-1', 'replace').decode('latin-1')

            if "DECISION: REJECT" in safe_line:
                pdf.set_text_color(200, 0, 0)
                pdf.cell(0, 10, txt=safe_line, ln=True)
                pdf.set_text_color(0, 0, 0)
            elif "DECISION: PROCEED" in safe_line:
                pdf.set_text_color(0, 150, 0)
                pdf.cell(0, 10, txt=safe_line, ln=True)
                pdf.set_text_color(0, 0, 0)
            elif "--- SECTION:" in safe_line or "SECTION TITLE:" in safe_line:
                pdf.ln(5)
                pdf.cell(0, 10, txt=safe_line, ln=True)
            else:
                pdf.multi_cell(0, 5, safe_line)

        return pdf.output(dest="S").encode("latin-1", "replace")

    except Exception as e:
        # --- RESCUE MODE ---
        # Generate a VALID PDF with error info (Not text bytes)
        try:
            rescue = FPDF()
            rescue.add_page()
            rescue.set_font("Arial", "", 12)

            rescue.set_text_color(200, 0, 0)
            rescue.cell(0, 10, "PDF Generation Error - Fallback Mode", ln=True, align='C')
            rescue.set_text_color(0, 0, 0)
            rescue.ln(5)

            rescue.multi_cell(0, 5,
                              f"The formatted report could not be generated due to an error: {str(e)}\n\nBelow is the raw text content:\n\n")

            # Safe Encode content for Arial
            safe_content = full_report_text.encode('latin-1', 'replace').decode('latin-1')
            rescue.multi_cell(0, 5, safe_content)

            return rescue.output(dest="S").encode("latin-1", "replace")
        except:
            return b"Critical Error: Could not generate any PDF."


# ==============================================================================
# 6. CSV BATCH GENERATOR
# ==============================================================================
def create_batch_csv(paper_results_list):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Filename", "Decision", "Comments"])
    for p in paper_results_list:
        writer.writerow([p['filename'], p['decision'], p['notes']])
    return output.getvalue()