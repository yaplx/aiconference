import streamlit as st
import os
import io
import zipfile
import backend
import re
import headers_map as hm
from dotenv import load_dotenv
from conference_options import CONFERENCE_OPTIONS

# ==========================================
# 1. PAGE CONFIG & AUTHENTICATION
# ==========================================
st.set_page_config(page_title="Conference Desk Reviewer", page_icon="⚖️", layout="wide")
load_dotenv()

if "processing" not in st.session_state: st.session_state.processing = False
if "results" not in st.session_state: st.session_state.results = None


def check_password():
    secret_password = st.secrets.get("APP_PASSWORD") or os.getenv("APP_PASSWORD")
    if not secret_password: return True
    user_input = st.text_input("🔑 Enter Access Password", type="password")
    return user_input == secret_password


if not check_password():
    st.stop()

api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not api_key:
    st.error("🚨 API Key not found! Please configure secrets or .env")
    st.stop()

client = backend.get_openai_client(api_key)


# ==========================================
# 2. HELPER FUNCTIONS
# ==========================================
def create_zip_of_reports(results_list):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for item in results_list:
            audience_str = item.get('audience', 'Reviewer').title()
            pdf_name = f"Report_{audience_str}_{item['filename']}.pdf"
            zip_file.writestr(pdf_name, item['pdf_bytes'])

        if results_list and results_list[0].get('decision') != "N/A":
            csv_data = backend.report_generator.create_batch_csv(results_list)
            zip_file.writestr("Batch_Summary.csv", csv_data)
    return zip_buffer.getvalue()


# ==========================================
# 3. MAIN INTERFACE
# ==========================================
st.title("⚖️ AI Conference Reviewer")

c1, c2 = st.columns(2)
with c1:
    target_conference = "General Academic Standards"
    selected_option = st.selectbox("Target Conference Track", CONFERENCE_OPTIONS, disabled=st.session_state.processing)

    if selected_option == "Custom...":
        user_custom = st.text_input("Enter Conference Name:", disabled=st.session_state.processing)
        if user_custom.strip(): target_conference = user_custom
    elif selected_option != "General Quality Check":
        target_conference = selected_option

with c2:
    audience_selection = st.radio(
        "Generate Report For:",
        ["Internal Review Committee (Flags flaws)", "Paper Authors (Constructive feedback)"],
        disabled=st.session_state.processing
    )
    audience = "author" if "Authors" in audience_selection else "reviewer"

uploaded_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True,
                                  disabled=st.session_state.processing)
show_details = st.checkbox("Show details on screen (Enable Tabs)", value=True, disabled=st.session_state.processing)

if uploaded_files and not st.session_state.processing:
    if st.button("🚀 Start AI Review"):
        st.session_state.processing = True
        st.session_state.results = []
        st.rerun()

# ==========================================
# 4. PROCESSING LOGIC
# ==========================================
if st.session_state.processing and uploaded_files:
    progress_bar = st.progress(0)
    status_text = st.empty()
    temp_results = []

    for i, uploaded_file in enumerate(uploaded_files):
        status_text.text(f"Processing file {i + 1}/{len(uploaded_files)}: {uploaded_file.name}...")
        try:
            with st.status(f"📄 Processing: {uploaded_file.name}", expanded=show_details) as status:
                # --- Step 1: Extraction & Filtering ---
                uploaded_file.seek(0)
                sections = backend.extract_sections(uploaded_file)
                full_text_clean = backend.combine_section_content(sections)

                # Filter out Front/Back matter for detailed review
                reviewable_sections = []
                for s in sections:
                    clean_title = re.sub(r"^[\d\w]+\.\s*", "", s['title'].upper().strip())
                    mapped = hm.HEADER_MAP.get(clean_title, clean_title)
                    if mapped not in hm.FRONT_MATTER and mapped not in hm.BACK_MATTER:
                        reviewable_sections.append(s)

                # --- Step 2: UI Setup (Tabs) ---
                if show_details:
                    tab_names = ["🔍 First Pass"] + [s['title'] for s in reviewable_sections]
                    tabs = st.tabs(tab_names)
                    first_pass_tab, section_tabs = tabs[0], tabs[1:]
                else:
                    first_pass_tab, section_tabs = st.empty(), []

                # --- Step 3: First Pass ---
                with first_pass_tab:
                    st.info(f"Analyzing Abstract (Mode: {audience.title()})...")
                    first_pass_content = backend.evaluate_first_pass(
                        client, uploaded_file.name, full_text_clean[:4000], target_conference, audience
                    )
                    st.markdown(first_pass_content)

                # --- Step 4: Decision & Detailed Review ---
                generated_slug = uploaded_file.name.replace(".pdf", "")[:20].replace(" ", "_")
                report_log = f"CONFERENCE TRACK: {target_conference}\n\n--- FIRST PASS ---\n{first_pass_content}\n\n"
                saved_tabs_data = []
                flagged_items = []

                if "REJECT" in first_pass_content.upper():
                    decision = "REJECT"
                    notes = first_pass_content.split("REASON:")[
                        1].strip() if "REASON:" in first_pass_content else "Rejected"
                    if show_details: st.error("❌ Rejected at First Pass.")
                else:
                    # Detailed Review (Pods logic)
                    report_log += "--- SECTION ANALYSIS ---\n"
                    # Split into Pods using the mapping
                    pod1 = [s for s in reviewable_sections if
                            hm.HEADER_MAP.get(re.sub(r"^[\d\w]+\.\s*", "", s['title'].upper().strip()), "") in hm.POD_1]
                    pod2 = [s for s in reviewable_sections if s not in pod1]

                    for pod in [p for p in [pod1, pod2] if p]:
                        pod_titles = ", ".join([s['title'] for s in pod])
                        st.write(f"Reviewing: {pod_titles}...")
                        batch_feedbacks = backend.generate_batch_review(client, pod, uploaded_file.name,
                                                                        target_conference, audience)

                        for sec in pod:
                            feedback = batch_feedbacks.get(sec['title'], "Review failed.")
                            report_log += f"\n--- SECTION: {sec['title']} ---\n{feedback}\n"
                            saved_tabs_data.append({"title": sec['title'], "content": feedback})

                            if show_details:
                                # Safe index lookup
                                try:
                                    tab_idx = reviewable_sections.index(sec)
                                    with section_tabs[tab_idx]:
                                        st.markdown(feedback)
                                except (ValueError, IndexError):
                                    pass

                            if any(k in feedback for k in
                                   ["ACCEPT WITH SUGGESTIONS", "REJECT", "REVISIONS RECOMMENDED"]):
                                flagged_items.append(sec['title'])

                    decision = "Accept w/ Suggestions" if flagged_items else "Accept"
                    notes = f"Issues in: {', '.join(flagged_items)}" if flagged_items else "Standard Review."

                # --- Step 5: Report Generation ---
                pdf_bytes = backend.create_pdf(report_log, filename=generated_slug, audience=audience)
                temp_results.append({
                    'filename': generated_slug, 'decision': decision, 'notes': notes,
                    'report_text': report_log, 'pdf_bytes': pdf_bytes,
                    'first_pass_content': first_pass_content, 'saved_tabs_data': saved_tabs_data,
                    'audience': audience
                })
                status.update(label=f"✅ Finished: {uploaded_file.name}", state="complete")

        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}")
        progress_bar.progress((i + 1) / len(uploaded_files))

    st.session_state.results = temp_results
    st.session_state.processing = False
    st.rerun()

# ==========================================
# 5. RESULTS DISPLAY
# ==========================================
if st.session_state.results:
    st.divider()
    st.header("📥 Reviews Completed")

    if len(st.session_state.results) > 1:
        zip_data = create_zip_of_reports(st.session_state.results)
        st.download_button("📦 Download All Reports (ZIP)", zip_data, "Review_Batch.zip", "application/zip",
                           type="primary")
        st.divider()

    for res in st.session_state.results:
        icon = "✅" if "Accept" in res['decision'] else "⚠️" if "Suggestions" in res['decision'] or "Revisions" in res[
            'decision'] else "❌"
        with st.expander(f"{icon} {res['filename']}  |  Decision: {res['decision']}", expanded=True):
            c1, c2 = st.columns([1, 4])
            with c1:
                st.download_button("⬇️ Download PDF", res['pdf_bytes'], f"Report_{res['filename']}.pdf",
                                   "application/pdf", type="primary")
            with c2:
                if res['notes']: st.info(f"**Notes:** {res['notes']}")

            st.divider()
            tab_titles = ["🔍 First Pass"] + [s['title'] for s in res['saved_tabs_data']]
            result_tabs = st.tabs(tab_titles)
            with result_tabs[0]:
                st.markdown(res['first_pass_content'])
            for i, sec_data in enumerate(res['saved_tabs_data']):
                with result_tabs[i + 1]:
                    st.markdown(sec_data['content'])

    if st.button("Start New Review"):
        st.session_state.results = None
        st.rerun()