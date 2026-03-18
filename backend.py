import re
import io
import csv
import document_reader
import getai
import report_generator
import headers_map as hm


# ==========================================
# 1. CORE BRIDGE FUNCTIONS
# ==========================================

def get_openai_client(api_key):
    """Bridge to the AI module"""
    return getai.get_openai_client(api_key)


def extract_sections(uploaded_file):
    """Bridge to the Reader module"""
    return document_reader.extract_sections_visual(uploaded_file)


def create_pdf(full_report, filename, audience):
    """Bridge to the Report module"""
    return report_generator.create_pdf_report(full_report, filename, audience)


def create_zip(results_list):
    """Bridge to the Report module"""
    return report_generator.create_zip_of_reports(results_list)


def combine_section_content(sections):
    """Joins all text for the First Pass check"""
    return "\n".join([f"--- {s['title']} ---\n{s['content']}" for s in sections])


# ==========================================
# 2. THE "BRAIN" (Workflow Logic)
# ==========================================

def run_full_workflow(client, uploaded_file, conference, audience):
    """
    Handles the entire process for one paper.
    This is what makes UI.py look tidy.
    """
    # 1. Extract
    uploaded_file.seek(0)
    sections = extract_sections(uploaded_file)
    full_text_clean = combine_section_content(sections)

    # 2. First Pass
    first_pass_content = getai.evaluate_first_pass(
        client, uploaded_file.name, full_text_clean[:4000], conference, audience
    )

    # 3. Decision & Detailed Review
    report_log = f"\n\n--- FIRST PASS ---\n{first_pass_content}\n\n"
    saved_tabs_data = []
    flagged_items = []

    if "REJECT" in first_pass_content.upper():
        decision = "REJECT"
        notes = _extract_reason(first_pass_content)
    else:
        # Filter sections for PODS
        valid_sections = filter_main_body_sections(sections)

        # Split into Pods
        pod1 = [s for s in valid_sections if _get_mapped_name(s['title']) in hm.POD_1]
        pod2 = [s for s in valid_sections if s not in pod1]

        for pod in [p for p in [pod1, pod2] if p]:
            batch_feedbacks = getai.generate_batch_review(
                client, pod, uploaded_file.name, conference, audience
            )

            for sec in pod:
                feedback = batch_feedbacks.get(sec['title'], "Review failed.")
                report_log += f"\n--- SECTION: {sec['title']} ---\n{feedback}\n"
                saved_tabs_data.append({"title": sec['title'], "content": feedback})

                if any(k in feedback for k in ["REJECT", "REVISIONS RECOMMENDED", "SUGGESTIONS"]):
                    flagged_items.append(sec['title'])

        decision = "Accept w/ Suggestions" if flagged_items else "Accept"
        notes = f"Issues in: {', '.join(flagged_items)}" if flagged_items else "Standard Review."

    # 4. Final PDF
    slug = uploaded_file.name.replace(".pdf", "")[:20].replace(" ", "_")
    pdf_bytes = create_pdf(report_log, filename=slug, audience=audience)

    return {
        'filename': slug,
        'decision': decision,
        'notes': notes,
        'report_text': report_log,
        'pdf_bytes': pdf_bytes,
        'first_pass_content': first_pass_content,
        'saved_tabs_data': saved_tabs_data,
        'audience': audience
    }


# ==========================================
# 3. INTERNAL HELPERS
# ==========================================

def filter_main_body_sections(sections):
    """Filters out Abstract and References"""
    return [s for s in sections if is_reviewable(s['title'])]


def is_reviewable(title):
    mapped = _get_mapped_name(title)
    return mapped not in hm.FRONT_MATTER and mapped not in hm.BACK_MATTER


def _get_mapped_name(title):
    clean_title = re.sub(r"^[\d\w]+\.\s*", "", title.upper().strip())
    return hm.HEADER_MAP.get(clean_title, clean_title)


def _extract_reason(text):
    if "REASON:" in text:
        return text.split("REASON:")[1].strip()
    return "Rejected at First Pass"