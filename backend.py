import re
import headers_map as hm
import getai
import document_reader
import report_generator
import streamlit as st


def process_paper_workflow(client, uploaded_file, conference, audience):
    """The 'Brain' of the operation: Handles the logic previously clogging up UI.py"""
    # 1. Extraction
    sections = document_reader.extract_sections_visual(uploaded_file)
    full_text = "\n".join([s['content'] for s in sections])

    # 2. Filtering
    valid_sections = [s for s in sections if is_main_body(s['title'])]

    # 3. First Pass
    first_pass = getai.evaluate_first_pass(client, uploaded_file.name, full_text[:4000], conference, audience)

    # 4. Detailed Review (if not rejected)
    saved_tabs = []
    if "REJECT" not in first_pass.upper():
        # Batch review logic remains here, kept away from UI
        feedback_map = getai.generate_batch_review(client, valid_sections, uploaded_file.name, conference, audience)
        saved_tabs = [{"title": k, "content": v} for k, v in feedback_map.items()]

    # 5. Generate PDF
    report_log = f"FIRST PASS:\n{first_pass}\n\n" + "\n".join([f"{t['title']}: {t['content']}" for t in saved_tabs])
    pdf = report_generator.create_pdf_report(report_log, uploaded_file.name, audience)

    return {
        "filename": uploaded_file.name,
        "first_pass_content": first_pass,
        "saved_tabs_data": saved_tabs,
        "pdf_bytes": pdf,
        "decision": "REJECT" if "REJECT" in first_pass.upper() else "PROCEED"
    }


def is_main_body(title):
    clean = re.sub(r"^[\d\w]+\.\s*", "", title.upper().strip())
    mapped = hm.HEADER_MAP.get(clean, clean)
    return mapped not in hm.FRONT_MATTER and mapped not in hm.BACK_MATTER


def render_ui_results(results):
    """Moves the lengthy 'Results' UI code here to keep UI.py tiny"""
    for res in results:
        with st.expander(f"📄 {res['filename']}"):
            st.write(res['first_pass_content'])
            # ... additional UI rendering ...