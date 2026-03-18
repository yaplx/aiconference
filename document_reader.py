import fitz  # PyMuPDF
import re
import headers_map as hm
from configurator import roman_to_int, IGNORE_CAPTION_KEYWORDS


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
    current_section = {"title": "PREAMBLE", "content": ""}
    expected_number = 1
    seen_mapped_titles = set()
    in_front_matter = True

    i = 0
    while i < len(all_lines):
        raw_line = all_lines[i]
        if re.match(r'^\d+$', raw_line):  # Skip standalone line numbers
            i += 1
            continue

        candidate_lines = [raw_line]
        strip_match = re.match(r'^\d+\s+(.*)$', raw_line)
        if strip_match: candidate_lines.append(strip_match.group(1))

        detected_header = False
        num_str, phrase, is_numbered = "", "", False
        skip_next_line = False

        for line in candidate_lines:
            if detected_header: break
            p_num, p_phrase = _parse_header_components(line)
            if p_num and _is_valid_numbered_header(p_num, p_phrase, expected_number):
                detected_header, is_numbered, num_str, phrase = True, True, p_num, p_phrase
            elif not detected_header and i + 1 < len(all_lines):
                num_match = re.match(r"^([IVXLCDMivxlcdm]+|\d+)(\.?)$", line)
                if num_match:
                    next_line = all_lines[i + 1].strip()
                    nl_match = re.match(r'^\d+\s+(.*)$', next_line)
                    if nl_match: next_line = nl_match.group(1)
                    if len(next_line) < 30 and next_line and next_line[0].isupper():
                        if _is_valid_numbered_header(num_match.group(1), next_line, expected_number):
                            detected_header, is_numbered, num_str, phrase, skip_next_line = True, True, num_match.group(
                                1), next_line, True

            if not detected_header:
                mapped_title = _get_mapped_title(line)
                if mapped_title: detected_header, phrase = True, mapped_title

        if detected_header:
            core_title = _get_mapped_title(phrase)
            if in_front_matter:
                if is_numbered or (core_title in hm.POD_1):
                    in_front_matter = False
                elif core_title in ["METHOD", "EXPERIMENT", "RESULT", "DISCUSSION", "CONCLUSION"]:
                    detected_header = False
            if detected_header and core_title:
                if core_title in seen_mapped_titles and core_title not in (hm.FRONT_MATTER + hm.BACK_MATTER):
                    detected_header = False
                else:
                    seen_mapped_titles.add(core_title)

        if detected_header:
            if current_section["content"].strip(): sections.append(current_section)
            current_section = {"title": f"{num_str}. {phrase}" if is_numbered else phrase, "content": ""}
            if is_numbered: expected_number += 1
            if skip_next_line: i += 1
        else:
            current_section["content"] += raw_line + " "
        i += 1

    if current_section["content"].strip(): sections.append(current_section)
    return sections