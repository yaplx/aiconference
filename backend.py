import re
import io
import csv
import zipfile
import streamlit as st
import document_reader
import getai
import report_generator
import headers_map as hm


# ==========================================
# 1. CORE BRIDGE FUNCTIONS
# ==========================================

def get_openai_client(api_key):
    return getai.get_openai_client(api_key)


def extract_sections(uploaded_file):
    return document_reader.extract_sections_visual(uploaded_file)


def combine_section_content(sections):
    return "\n".join([f"--- {s['title']} ---\n{s['content']}" for s in sections])


def create_pdf(full_report, filename, audience):
    return report_generator.create_pdf_report(full_report, filename, audience)


# ==========================================
# 2. LOGIC HELPERS (Tidying up the UI)
# ==========================================

def is_reviewable(title):
    """Checks if a section should be reviewed by AI (ignores References/Appendix)"""
    clean_title = re.sub(r"^[\d\w]+\.\s*", "", title.upper().strip())
    mapped = hm.HEADER_MAP.get(clean_title, clean_title)
    return mapped not in hm.FRONT_MATTER and mapped not in hm.BACK_MATTER


def create_zip(results_list):
    """Generates a ZIP file for batch downloads"""
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for item in results_list:
            audience_str = item.get('audience', 'Reviewer').title()
            pdf_name = f"Report_{audience_str}_{item['filename']}.pdf"
            zip_file.writestr(pdf_name, item['pdf_bytes'])

        if results_list and results_list[0].get('decision') != "N/A":
            csv_data = report_generator.create_batch_csv(results_list)
            zip_file.writestr("Batch_Summary.csv", csv_data)
    return zip_buffer.getvalue()


# ==========================================
# 3. UI RENDERING (Fixes the AttributeError)
# ==========================================

def render_ui_results(results):
    """
    This function handles the 'lengthy' display logic.
    It keeps UI.py clean by putting the expanders and tabs here.
    """
    st.divider()
    st.header("📥 Reviews Completed")

    if len(results) > 1:
        zip_data = create_zip(results)
        st.download_button("⬇️ Download All (.zip)", zip_data, "All_Reviews.zip", "application/zip", type="primary")
        st.divider()

    for res in results:
        # Determine Icon
        icon = "✅" if "Accept" in res['decision'] else "⚠️" if "Suggestions" in res['decision'] or "Revisions" in res[
            'decision'] else "❌"

        with st.expander(f"{icon} {res['filename']}  |  Decision: {res['decision']}", expanded=True):
            c1, c2 = st.columns([1, 4])
            with c1:
                st.download_button("⬇️ Download PDF", res['pdf_bytes'], f"Report_{res['filename']}.pdf",
                                   "application/pdf", type="primary")
            with c2:
                if res.get('notes'): st.info(f"**Notes:** {res['notes']}")

            st.divider()

            # Setup Tabs for the individual report
            tab_titles = ["🔍 First Pass"] + [s['title'] for s in res.get('saved_tabs_data', [])]
            result_tabs = st.tabs(tab_titles)

            with result_tabs[0]:
                st.markdown(res.get('first_pass_content', "No data."))

            for i, sec_data in enumerate(res.get('saved_tabs_data', [])):
                with result_tabs[i + 1]:
                    st.markdown(sec_data['content'])

    if st.button("Start New Review"):
        st.session_state.results = None
        st.rerun()