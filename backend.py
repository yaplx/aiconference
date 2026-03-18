import fitz  # PyMuPDF
import re
import csv
import io
from openai import OpenAI
from fpdf import FPDF
import prompts
import headers_map as hm
from disclaimer import DISCLAIMERS

# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
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
    if clean_upper in hm.HEADER_MAP: return hm.HEADER_MAP[clean_upper]
    return None


def combine_section_content(sections):
    full_text = []
    for sec in sections:
        full_text.append(f"--- {sec['title']} ---")
        full_text.append(sec['content'])
    return "\n".join(full_text)


def sanitize_text_for_pdf(text):
    replacements = {
        u'\u2018': "'", u'\u2019': "'", u'\u201c': '"', u'\u201d': '"',
        u'\u2013': '-', u'\u2014': '-', u'\u2212': '-', "**": ""
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


# ==============================================================================
# 3. EXTRACTION (Line Cleaner & Zone Lockout Included)
# ==============================================================================
def extract_sections_visual(uploaded_file):
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

    seen_mapped_titles = set()
    FRONT_BACK_MATTER = hm.FRONT_MATTER + hm.BACK_MATTER

    # State tracking for Zone Lockout
    in_front_matter = True
    UNLOCKERS = hm.POD_1  # Introduction, Background, etc. act as unlockers

    i = 0
    while i < len(all_lines):
        raw_line = all_lines[i]

        # --- 1. Ignore Standalone Line Numbers ---
        if re.match(r'^\d+$', raw_line):
            i += 1
            continue

        # --- 2. Generate Candidate Lines (Raw vs Stripped) ---
        candidate_lines = [raw_line]
        strip_match = re.match(r'^\d+\s+(.*)$', raw_line)
        if strip_match:
            candidate_lines.append(strip_match.group(1))

        detected_header = False
        num_str, phrase, is_numbered = "", "", False
        skip_next_line = False

        for line in candidate_lines:
            if detected_header: break

            p_num, p_phrase = _parse_header_components(line)
            if p_num and _is_valid_numbered_header(p_num, p_phrase, expected_number):
                detected_header = True
                is_numbered = True
                num_str = p_num
                phrase = p_phrase
            elif not detected_header and i + 1 < len(all_lines):
                num_match = re.match(r"^([IVXLCDMivxlcdm]+|\d+)(\.?)$", line)
                if num_match:
                    potential_num = num_match.group(1)
                    next_line = all_lines[i + 1].strip()

                    # Also strip potential line numbers from split lines
                    nl_match = re.match(r'^\d+\s+(.*)$', next_line)
                    if nl_match:
                        next_line = nl_match.group(1)

                    if len(next_line) < 30 and next_line and next_line[0].isupper():
                        if _is_valid_numbered_header(potential_num, next_line, expected_number):
                            detected_header = True
                            is_numbered = True
                            num_str = potential_num
                            phrase = next_line
                            skip_next_line = True

            if not detected_header:
                mapped_title = _get_mapped_title(line)
                if mapped_title:
                    detected_header = True
                    is_numbered = False
                    phrase = mapped_title

        # --- Apply Protections ---
        if detected_header:
            core_title = _get_mapped_title(phrase)

            # Zone Lockout Protection (Protects Structured Abstracts)
            if in_front_matter:
                # Unlock if we hit an official starting section or any numbered section
                if is_numbered or (core_title in UNLOCKERS):
                    in_front_matter = False
                # If we see standard body headers but are still locked in the abstract, ignore them
                elif core_title in ["METHOD", "EXPERIMENT", "RESULT", "DISCUSSION", "CONCLUSION"]:
                    detected_header = False

                    # Duplicate Prevention ONLY
            if detected_header and core_title:
                if core_title in seen_mapped_titles and core_title not in FRONT_BACK_MATTER:
                    detected_header = False
                else:
                    seen_mapped_titles.add(core_title)

        # --- Apply Header ---
        if detected_header:
            if current_section["content"].strip(): sections.append(current_section)
            if is_numbered:
                current_section = {"title": f"{num_str}. {phrase}", "content": ""}
                expected_number += 1
            else:
                current_section = {"title": phrase, "content": ""}

            if skip_next_line:
                i += 1
        else:
            # Safely append the raw line to the content block so no data is lost
            current_section["content"] += raw_line + " "

        i += 1

    if current_section["content"].strip(): sections.append(current_section)
    return sections


# ==============================================================================
# 4. REVIEW LOGIC (BATCH XML APPROACH)
# ==============================================================================
def evaluate_first_pass(client, paper_title, abstract_text, conference_name, audience):
    prompt = prompts.get_first_pass_prompt(conference_name, paper_title, abstract_text, audience)
    try:
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error with gpt-5: {str(e)}"


def generate_batch_review(client, sections_list, paper_title, conference_name, audience):
    if not sections_list: return {}

    sections_info = []
    for sec in sections_list:
        clean_name = sec['title'].upper().strip()
        clean_name = re.sub(r"^[\d\w]+\.\s*", "", clean_name)
        focus = prompts.get_section_focus(clean_name, audience)
        sections_info.append({
            "title": sec['title'],
            "focus": focus,
            "content": sec['content']
        })

    prompt = prompts.get_batch_review_prompt(conference_name, paper_title, sections_info, audience)

    try:
        response = client.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": prompt}]
        )
        raw_output = response.choices[0].message.content

        xml_results = {}
        pattern = re.compile(r'<REVIEW\s+section=["\']?(.*?)["\']?>(.*?)</REVIEW>', re.IGNORECASE | re.DOTALL)
        matches = pattern.findall(raw_output)

        for match_title, feedback in matches:
            xml_results[match_title.strip().upper()] = feedback.strip()

        final_results = {}
        for sec in sections_list:
            title_upper = sec['title'].strip().upper()
            matched_content = "Status: ACCEPT WITH SUGGESTIONS\n\nFLAGGED ISSUES:\n- AI failed to format this section's review correctly."

            for k in xml_results.keys():
                if title_upper in k or k in title_upper:
                    matched_content = xml_results[k]
                    break
            final_results[sec['title']] = matched_content

        return final_results
    except Exception as e:
        return {sec['title']: f"Error: {str(e)}" for sec in sections_list}


# ==============================================================================
# 5. PDF GENERATION
# ==============================================================================
def create_pdf_report(full_report_text, filename="document.pdf", audience="reviewer"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", '', 11)

    # --- TITLE ---
    pdf.set_font("Arial", 'B', 16)
    title_text = "AI Paper Desk Review (Internal)" if audience == "reviewer" else "AI Paper Feedback Report (Author)"
    pdf.cell(0, 10, txt=title_text, ln=True, align='C')
    pdf.ln(3)

    # --- DISCLAIMER ---
    pdf.set_font("Arial", '', 8)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 4, txt=DISCLAIMERS[audience], align='L')
    pdf.ln(10)

    # --- METADATA ---
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", '', 14)
    pdf.cell(0, 10, txt=f"REPORT FOR: {filename}", ln=True, align='L')
    pdf.ln(2)

    # --- BODY ---
    pdf.set_font("Arial", '', 12)
    clean_text = sanitize_text_for_pdf(full_report_text)
    lines = clean_text.split('\n')
    for line in lines:
        safe_line = line.strip()
        safe_line = safe_line.encode('latin-1', 'replace').decode('latin-1')

        if "DECISION:" in safe_line or "--- SECTION:" in safe_line:
            pdf.ln(5)
            pdf.cell(0, 10, txt=safe_line, ln=True)
        else:
            pdf.multi_cell(0, 5, safe_line)

    return pdf.output(dest="S").encode("latin-1", "replace")


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