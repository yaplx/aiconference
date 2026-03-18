import streamlit as st
import os
import zipfile
import io
import backend
import re
import headers_map as hm  # Imported the new map
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
    if "APP_PASSWORD" in st.secrets:
        secret_password = st.secrets["APP_PASSWORD"]
    elif os.getenv("APP_PASSWORD"):
        secret_password = os.getenv("APP_PASSWORD")
    else:
        return True

    user_input = st.text_input("🔑 Enter Access Password", type="password")
    if user_input == secret_password:
        return True
    return False


if not check_password():
    st.stop()

api_key = None
if "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]
elif os.getenv("OPENAI_API_KEY"):
    api_key = os.getenv("OPENAI_API_KEY")

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
            csv_data = backend.create_batch_csv(results_list)
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
            file_container = st.expander(f"📄 Processing: {uploaded_file.name}",
                                         expanded=True) if show_details else st.empty()

            saved_tabs_data = []
            first_pass_content = ""
            report_log = ""
            decision = "Pending"
            notes = ""

            with file_container:
                uploaded_file.seek(0)
                sections = backend.extract_sections_visual(uploaded_file)
                full_text_clean = backend.combine_section_content(sections)

                # Dynamically filter valid sections using headers_map
                valid_sections = []
                for s in sections:
                    clean_title = s['title'].upper().strip()
                    clean_title = re.sub(r"^[\d\w]+\.\s*", "", clean_title)
                    mapped = hm.HEADER_MAP.get(clean_title, clean_title)
                    if mapped not in hm.FRONT_MATTER + hm.BACK_MATTER:
                        valid_sections.append(s)

                tab_names = ["🔍 First Pass"] + [s['title'] for s in valid_sections]

                if show_details:
                    tabs = st.tabs(tab_names)
                    first_pass_tab = tabs[0]
                    section_tabs = tabs[1:]
                else:
                    first_pass_tab = st.empty()
                    section_tabs = []

                # First Pass
                with first_pass_tab:
                    st.info(f"Analyzing Abstract (Mode: {audience.title()})...")
                    first_pass_content = backend.evaluate_first_pass(
                        client, uploaded_file.name, full_text_clean[:4000], target_conference, audience
                    )
                    st.markdown(first_pass_content)

                # SLUG EXTRACTION
                generated_slug = uploaded_file.name.replace(".pdf", "")[:20].replace(" ", "_")
                for line in first_pass_content.split('\n'):
                    if line.strip().startswith("SLUG:"):
                        raw_slug = line.split("SLUG:")[1].strip()
                        generated_slug = re.sub(r'[^A-Za-z0-9_-]', '', raw_slug.replace(' ', '_'))
                        break

                report_log = f"\n\n--- FIRST PASS ---\n{first_pass_content}\n\n"
                decision = "PROCEED"
                notes = "Standard review."

                if "REJECT" in first_pass_content:
                    decision = "REJECT"
                    report_log += "**Skipping detailed section review due to rejection.**"
                    if "REASON:" in first_pass_content:
                        try:
                            notes = first_pass_content.split("REASON:")[1].strip()
                        except:
                            notes = "Rejected"
                    if show_details: st.error("❌ Rejected.")
                else:
                    # Second Pass - BATCH PROCESSING
                    report_log += "--- SECTION ANALYSIS ---\n"
                    flagged_items = []

                    # Dynamically sort into Pods using headers_map
                    pod1 = []
                    pod2 = []

                    for sec in valid_sections:
                        clean_title = sec['title'].upper().strip()
                        clean_title = re.sub(r"^[\d\w]+\.\s*", "", clean_title)
                        mapped = hm.HEADER_MAP.get(clean_title, clean_title)

                        if mapped in hm.POD_1:
                            pod1.append(sec)
                        else:
                            pod2.append(sec)

                    pods = [p for p in [pod1, pod2] if p]

                    for pod in pods:
                        pod_titles = ", ".join([s['title'] for s in pod])

                        with st.spinner(f"Reviewing in batch context: {pod_titles}..."):
                            batch_feedbacks = backend.generate_batch_review(
                                client, pod, uploaded_file.name, target_conference, audience
                            )

                        for sec in pod:
                            feedback = batch_feedbacks.get(sec['title'], "Review failed or no output generated.")

                            tab_idx = valid_sections.index(sec)
                            current_tab = section_tabs[tab_idx] if show_details else st.empty()
                            with current_tab:
                                st.markdown(feedback)

                            report_log += f"\n--- SECTION: {sec['title']} ---\n{feedback}\n"
                            saved_tabs_data.append({"title": sec['title'], "content": feedback})

                            if any(k in feedback for k in
                                   ["ACCEPT WITH SUGGESTIONS", "REJECT", "REVISIONS RECOMMENDED"]):
                                flagged_items.append(sec['title'])

                    if flagged_items:
                        decision = "Accept w/ Suggestions" if audience == "reviewer" else "Revisions Recommended"
                        notes = f"Issues in: {', '.join(flagged_items)}"
                    else:
                        decision = "Accept" if audience == "reviewer" else "Meets Desk Requirements"

            pdf_bytes = backend.create_pdf_report(report_log, filename=generated_slug, audience=audience)

            temp_results.append({
                'filename': generated_slug,
                'original_filename': uploaded_file.name,
                'decision': decision,
                'notes': notes,
                'report_text': report_log,
                'pdf_bytes': pdf_bytes,
                'first_pass_content': first_pass_content,
                'saved_tabs_data': saved_tabs_data,
                'audience': audience
            })

        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}")

        progress_bar.progress((i + 1) / len(uploaded_files))

    st.session_state.results = temp_results
    st.session_state.processing = False
    st.rerun()

# ==========================================
# 5. RESULTS & DOWNLOADS
# ==========================================
if st.session_state.results:
    st.divider()
    st.header("📥 Reviews Completed")
    results = st.session_state.results

    if len(results) > 1:
        st.info("📦 **Batch Download Available**")
        zip_data = create_zip_of_reports(results)
        st.download_button("⬇️ Download All (.zip)", zip_data, "All_Reviews.zip", "application/zip", type="primary")
        st.divider()

    for res in results:
        icon = "✅" if "Accept" in res['decision'] or "Meets" in res['decision'] else "⚠️" if "Suggestions" in res[
            'decision'] or "Revisions" in res['decision'] else "❌"
        with st.expander(f"{icon} {res['filename']}  |  Decision: {res['decision']}", expanded=True):
            c1, c2 = st.columns([1, 4])
            with c1:
                audience_str = res.get('audience', 'Reviewer').title()
                download_filename = f"Report_{audience_str}_{res['filename']}.pdf"

                st.download_button("⬇️ Download PDF Report", res['pdf_bytes'], download_filename,
                                   "application/pdf", type="primary")
            with c2:
                if res['notes']: st.info(f"**Notes:** {res['notes']}")

            st.divider()

            saved_sections = res.get('saved_tabs_data', [])
            first_pass = res.get('first_pass_content', "")

            if saved_sections or first_pass:
                tab_titles = ["🔍 First Pass"] + [s['title'] for s in saved_sections]
                result_tabs = st.tabs(tab_titles)
                with result_tabs[0]:
                    st.markdown(first_pass if first_pass else "No data.")
                for i, sec_data in enumerate(saved_sections):
                    with result_tabs[i + 1]:
                        st.markdown(sec_data['content'])
            else:
                st.text_area("Full Report Log", res['report_text'], height=200)

    st.divider()
    if st.button("Start New Review"):
        st.session_state.results = None
        st.rerun()