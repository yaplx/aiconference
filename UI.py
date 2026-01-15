import streamlit as st
import os
import zipfile
import io
import backend
from dotenv import load_dotenv

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
            pdf_name = f"Report_{item['filename']}.pdf"
            zip_file.writestr(pdf_name, item['pdf_bytes'])

        if results_list and results_list[0].get('decision') != "N/A":
            csv_data = backend.create_batch_csv(results_list)
            zip_file.writestr("Batch_Summary.csv", csv_data)
    return zip_buffer.getvalue()


# ==========================================
# 3. MAIN INTERFACE
# ==========================================
st.title("⚖️ AI Conference Reviewer")

target_conference = "General Academic Standards"
conference_options = [
    "General Quality Check",
    "Learning Sciences, Educational Neuroscience, and CSCL",
    "Mobile, Ubiquitous & Contextual Learning",
    "Joyful Learning, Educational Games, and Digital Toys",
    "Technology Applications in Higher Education",
    "Technology-enhanced Language and Humanities Learning",
    "AI in Education Applications and Practices",
    "Learning Analytics and Assessment",
    "STEM and Maker Education",
    "Educational Technology: Innovations & Policies",
    "Custom..."
]

selected_option = st.selectbox("Target Conference Track", conference_options, disabled=st.session_state.processing)
if selected_option == "Custom...":
    user_custom = st.text_input("Enter Conference Name:", disabled=st.session_state.processing)
    if user_custom.strip(): target_conference = user_custom
elif selected_option != "General Quality Check":
    target_conference = selected_option

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

    # We iterate through files
    for i, uploaded_file in enumerate(uploaded_files):
        status_text.text(f"Processing file {i + 1}/{len(uploaded_files)}: {uploaded_file.name}...")
        try:
            # UI Setup
            file_container = st.expander(f"📄 Processing: {uploaded_file.name}",
                                         expanded=True) if show_details else st.empty()

            # Variables to hold data for the final session state
            saved_tabs_data = []
            first_pass_content = ""
            report_log = ""
            decision = "Pending"
            notes = ""

            with file_container:
                uploaded_file.seek(0)
                sections = backend.extract_sections_visual(uploaded_file)
                full_text_clean = backend.combine_section_content(sections)

                valid_sections = [s for s in sections if
                                  not any(skip in s['title'].upper() for skip in backend.SKIP_REVIEW_SECTIONS)]
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
                    st.info("Analyzing Abstract...")
                    first_pass_content = backend.evaluate_first_pass(client, uploaded_file.name, full_text_clean[:4000],
                                                                     target_conference)
                    st.markdown(first_pass_content)

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
                    # Second Pass
                    report_log += "--- SECTION ANALYSIS ---\n"
                    flagged_items = []
                    for idx, sec in enumerate(valid_sections):
                        current_tab = section_tabs[idx] if show_details else st.empty()
                        with current_tab:
                            with st.spinner(f"Analyzing {sec['title']}..."):
                                feedback = backend.generate_section_review(client, sec['title'], sec['content'],
                                                                           uploaded_file.name)
                            if feedback:
                                st.markdown(feedback)
                                report_log += f"\n--- SECTION: {sec['title']} ---\n{feedback}\n"
                                saved_tabs_data.append({"title": sec['title'], "content": feedback})
                                if "FLAGGED ISSUES" in feedback and "(None)" not in feedback:
                                    flagged_items.append(sec['title'])

                    if flagged_items:
                        decision = "Accept w/ Suggestions"
                        notes = f"Issues in: {', '.join(flagged_items)}"
                    else:
                        decision = "Accept"

            # Generate PDF (Safe Mode)
            pdf_bytes = backend.create_pdf_report(report_log, filename=uploaded_file.name)

            # Append results safely
            temp_results.append({
                'filename': uploaded_file.name,
                'decision': decision,
                'notes': notes,
                'report_text': report_log,
                'pdf_bytes': pdf_bytes,
                'first_pass_content': first_pass_content,
                'saved_tabs_data': saved_tabs_data
            })

        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}")

        progress_bar.progress((i + 1) / len(uploaded_files))

    # SAVE RESULTS AND FINISH
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
        icon = "✅" if res['decision'] == "Accept" else "⚠️" if "Suggestions" in res['decision'] else "❌"
        with st.expander(f"{icon} {res['filename']}  |  Decision: {res['decision']}", expanded=True):
            c1, c2 = st.columns([1, 4])
            with c1:
                st.download_button("⬇️ Download PDF Report", res['pdf_bytes'], f"Report_{res['filename']}.pdf",
                                   "application/pdf", type="primary")
            with c2:
                if res['notes']: st.info(f"**Notes:** {res['notes']}")

            st.divider()

            # REBUILD TABS
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