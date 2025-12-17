import fitz  # PyMuPDF
import re
import os
from openai import OpenAI
from fpdf import FPDF


# --- 1. INITIALIZATION ---
def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


# --- 2. TEXT EXTRACTION ---
def extract_text_from_pdf_stream(uploaded_file):
    try:
        file_bytes = uploaded_file.read()
        doc = fitz.open(stream=file_bytes, filetype="pdf")

        all_lines = []
        for page in doc:
            text = page.get_text("text")
            raw_lines = text.split('\n')
            for line in raw_lines:
                clean = re.sub(r"^\\s*", "", line.strip())
                if clean:
                    all_lines.append(clean)

        doc.close()
        return all_lines
    except Exception as e:
        return []

    # --- 3. HYBRID PARSING LOGIC ---


def _is_level_1_numbering(line):
    arabic = r"^\d+\.\s+[A-Z]"
    roman = r"^(?=[MDCLXVI])M*(C[MD]|D?C{0,3})(X[CL]|L?X{0,3})(I[XV]|V?I{0,3})\.\s+[A-Z]"
    if re.match(arabic, line) or re.match(roman, line):
        return True
    return False


def split_into_sections(text_lines):
    HEADER_MAP = {
        "ABSTRACT": "ABSTRACT",
        "INTRODUCTION": "INTRODUCTION",
        "RELATED WORK": "RELATED WORK", "LITERATURE REVIEW": "RELATED WORK", "BACKGROUND": "RELATED WORK",
        "METHOD": "METHODOLOGY", "METHODS": "METHODOLOGY", "METHODOLOGY": "METHODOLOGY",
        "PROPOSED METHOD": "METHODOLOGY", "APPROACH": "METHODOLOGY",
        "EXPERIMENT": "EXPERIMENTS", "EXPERIMENTS": "EXPERIMENTS", "EVALUATION": "EXPERIMENTS",
        "RESULT": "RESULTS", "RESULTS": "RESULTS",
        "DISCUSSION": "DISCUSSION",
        "CONCLUSION": "CONCLUSION", "CONCLUSIONS": "CONCLUSION", "FUTURE WORK": "CONCLUSION"
    }
    STOP_KEYWORDS = ["REFERENCES", "BIBLIOGRAPHY", "APPENDIX", "APPENDICES", "ACKNOWLEDGEMENT"]

    sections = {}
    current_header = "PREAMBLE"
    sections[current_header] = []

    for line in text_lines:
        clean_line = line.strip()
        upper_line = clean_line.upper()
        clean_upper_no_num = re.sub(r"^[\d\.IVXivx]+\s+", "", upper_line).strip()

        is_stop = False
        for stop_word in STOP_KEYWORDS:
            if clean_upper_no_num.startswith(stop_word):
                is_stop = True
                break
        if is_stop: break

        is_new_header = False
        final_header_name = ""

        if clean_upper_no_num in HEADER_MAP:
            final_header_name = HEADER_MAP[clean_upper_no_num]
            is_new_header = True
        elif _is_level_1_numbering(clean_line):
            final_header_name = clean_line
            is_new_header = True

        if is_new_header:
            current_header = final_header_name
            if current_header not in sections:
                sections[current_header] = []
        else:
            sections[current_header].append(clean_line)

    if "PREAMBLE" in sections:
        del sections["PREAMBLE"]

    final_output = {k: "\n".join(v) for k, v in sections.items() if v}
    return final_output


# --- 4. AI REVIEW GENERATION (UPDATED FOR DECISION SUPPORT) ---
def generate_section_review(client, section_name, section_text, paper_title="Untitled Paper"):
    # Custom instructions based on section type
    context_instruction = ""
    if "METHOD" in section_name.upper():
        context_instruction = "Check for: Reproducibility gaps, missing equations, or vague algorithm steps."
    elif "RESULT" in section_name.upper():
        context_instruction = "Check for: Missing baselines, unclear metrics, or claims not supported by data."
    elif "INTRO" in section_name.upper():
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
            model="gpt-5",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error querying AI: {str(e)}"


# --- 5. PDF REPORT GENERATION (UPDATED LAYOUT) ---
def create_pdf_report(full_report_text):
    pdf = FPDF()
    pdf.add_page()

    font_path = os.path.join("dejavu-sans-ttf-2.37", "ttf", "DejaVuSans.ttf")
    font_family = "Arial"

    if os.path.exists(font_path):
        pdf.add_font('DejaVu', '', font_path, uni=True)
        font_family = 'DejaVu'
        # Bold font for titles (Simulated by using same font but we handle headers differently below)

    # --- TITLE ---
    pdf.set_font(font_family, '', 16)
    pdf.cell(0, 10, txt="AI-Optimized Reviewer Assistant Report", ln=True, align='C')
    pdf.ln(3)

    # --- DISCLAIMER ---
    pdf.set_font(font_family, '', 8)
    pdf.set_text_color(100, 100, 100)
    disclaimer_text = (
        "DISCLAIMER: This is an automated assistant tool. "
        "The 'RECOMMENDATION' is a suggestion based on structural and content analysis. "
        "The Human Reviewer must verify all 'FOCUS POINTS' manually."
    )
    pdf.multi_cell(0, 4, txt=disclaimer_text, align='C')
    pdf.ln(10)

    # --- MAIN CONTENT PARSER ---
    pdf.set_text_color(0, 0, 0)
    pdf.set_font(font_family, '', 12)

    # We process the text line by line to add basic formatting for the Recommendation
    lines = full_report_text.split('\n')

    for line in lines:
        clean_line = line.strip()

        # Highlight "SECTION:" headers
        if "--- SECTION:" in clean_line:
            pdf.ln(5)
            pdf.set_font(font_family, '', 14)  # Larger for headers
            pdf.cell(0, 10, txt=clean_line, ln=True)
            pdf.set_font(font_family, '', 12)  # Reset

        # Highlight "RECOMMENDATION:" lines
        elif "**RECOMMENDATION:**" in clean_line or "RECOMMENDATION:" in clean_line:
            pdf.set_font(font_family, '', 12)  # Use standard font but maybe add color/spacing

            # Simple color coding (Red for Reject, Green/Black for Accept) - Optional
            if "REJECT" in clean_line:
                pdf.set_text_color(200, 0, 0)  # Dark Red
            else:
                pdf.set_text_color(0, 100, 0)  # Dark Green

            pdf.cell(0, 10, txt=clean_line.replace("**", ""), ln=True)
            pdf.set_text_color(0, 0, 0)  # Reset to black

        # Standard Text
        else:
            # Handle wrapped text
            if font_family == 'DejaVu':
                pdf.multi_cell(0, 6, clean_line)  # Reduced line height for tighter list
            else:
                safe_text = clean_line.encode('latin-1', 'replace').decode('latin-1')
                pdf.multi_cell(0, 6, safe_text)

    return pdf.output(dest="S").encode("latin-1")