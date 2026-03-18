import document_reader
import getai
import report_generator
import re
import headers_map as hm


# ==========================================
# 1. CORE BRIDGE FUNCTIONS (UI calls these)
# ==========================================

def get_openai_client(api_key):
    return getai.get_openai_client(api_key)


def extract_sections(uploaded_file):
    return document_reader.extract_sections_visual(uploaded_file)


def create_pdf(full_report, filename, audience):
    return report_generator.create_pdf_report(full_report, filename, audience)


def create_zip(results_list):
    return report_generator.create_zip_of_reports(results_list)


# ==========================================
# 2. DATA PROCESSING (The "Tidying" Logic)
# ==========================================

def filter_reviewable_sections(sections):
    """
    Tidies up the UI by removing Front/Back matter
    and returning only the sections that need AI review.
    """
    valid = []
    for s in sections:
        clean_title = re.sub(r"^[\d\w]+\.\s*", "", s['title'].upper().strip())
        mapped = hm.HEADER_MAP.get(clean_title, clean_title)

        if mapped not in hm.FRONT_MATTER and mapped not in hm.BACK_MATTER:
            valid.append(s)
    return valid


def combine_section_content(sections):
    """Joins sections into one big string for the first-pass check"""
    return "\n".join([f"--- {s['title']} ---\n{s['content']}" for s in sections])


# ==========================================
# 3. AI ORCHESTRATION
# ==========================================

def evaluate_first_pass(client, paper_title, abstract_content, conf_choice, audience):
    # We could add extra logic here to 'clean' the abstract before sending to AI
    return getai.evaluate_first_pass(client, paper_title, abstract_content, conf_choice, audience)


def generate_batch_review(client, sections_list, paper_title, conf_choice, audience):
    # This calls the complex XML parsing logic inside getai.py
    return getai.generate_batch_review(client, sections_list, paper_title, conf_choice, audience)