import fitz  # PyMuPDF
import re
import os
from openai import OpenAI
from fpdf import FPDF
from collections import Counter


# --- 1. INITIALIZATION ---
def get_openai_client(api_key):
    return OpenAI(api_key=api_key)


# --- 2. ORIGINAL TEXT EXTRACTION (Legacy/Fallback) ---
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


# --- 3. NEW: VISUAL SECTIONING (Font Size + Bold) ---
def _get_body_font_size(doc):
    """
    Scans the document to find the most common font size (Body Text).
    Returns the body_size to set a baseline.
    """
    font_sizes = []

    # Scan max 5 pages to save time, or all if short
    for i, page in enumerate(doc):
        if i > 5: break
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        # Round to nearest integer to handle float precision (11.98 -> 12)
                        font_sizes.append(round(span["size"]))

    if not font_sizes:
        return 12  # Default fallback

    # The most common font size is likely the body text
    return Counter(font_sizes).most_common(1)[0][0]


def extract_sections_visual(uploaded_file):
    """
    Extracts sections based on Font Size and Bold formatting.
    Returns a list of dicts: [{'title': '...', 'content': '...'}]
    """
    # Reset file pointer and read bytes
    uploaded_file.seek(0)
    file_bytes = uploaded_file.read()

    doc = fitz.open(stream=file_bytes, filetype="pdf")

    # 1. Get stats to know what "Normal" looks like
    body_size = _get_body_font_size(doc)
    header_threshold = body_size + 0.5  # Threshold: anything larger than body

    sections = []
    current_section = {"title": "Preamble/Introduction", "content": ""}

    # Regex to catch numbered headers like "1. Introduction" or "2. RUNE"
    header_pattern = re.compile(r"^\d+\.\s+[A-Z]")

    for page in doc:
        blocks = page.get_text("dict")["blocks"]

        for block in blocks:
            if "lines" not in block: continue

            for line in block["lines"]:
                # Reconstruct line text from spans
                line_text = "".join([s["text"] for s in line["spans"]]).strip()
                if not line_text: continue

                # Check attributes (max size in line, and if any part is bold)
                max_size = max([s["size"] for s in line["spans"]])

                # Check for Bold (Flag 16 usually means bold, or font name contains 'Bold')
                is_bold = any([(s["flags"] & 16) or "Bold" in s["font"] for s in line["spans"]])

                # --- DECISION LOGIC: Is this a Header? ---
                is_header = False

                # Rule 1: Font size is larger than body text
                if max_size >= header_threshold:
                    is_header = True

                # Rule 2: It is Bold AND matches a pattern (e.g. "2. RUNE")
                elif is_bold and header_pattern.match(line_text):
                    is_header = True

                # Rule 3: Short bold lines (e.g. "Abstract", "References")
                elif is_bold and len(line_text.split()) < 6:
                    is_header = True

                # --- Save Data ---
                if is_header:
                    # Save the previous section if it has content
                    if current_section["content"].strip():
                        sections.append(current_section)

                    # Start a new section
                    current_section = {
                        "title": line_text,
                        "content": ""
                    }
                else:
                    # Append text to current section
                    current_section["content"] += line_text + " "

    # Append the final section
    if current_section["content"].strip():
        sections.append(current_section)

    doc.close()
    return sections


# --- 4. ORIGINAL: AI REVIEW GENERATION ---
def generate_section_review(client, section_name, section_text, paper_title="Untitled Paper"):
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
            model="gpt-4o",  # Updated model name for better availability
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error querying AI: {str(e)}"


# --- 5. PDF REPORT GENERATION ---
def create_pdf_report(full_report_text):
    pdf = FPDF()
    pdf.add_page()

    # Fallback to standard font if custom font missing
    font_family = "Arial"

    # --- TITLE ---
    pdf.set_font(font_family, 'B', 16)
    pdf.cell(0, 10, txt="AI-Optimized Reviewer Assistant Report", ln=True, align='C')
    pdf.ln(3)

    # --- MAIN CONTENT PARSER ---
    pdf.set_font(font_family, '', 10)

    # Simple line printing
    lines = full_report_text.split('\n')
    for line in lines:
        clean = line.strip().encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 5, clean)

    return pdf.output(dest="S").encode("latin-1")