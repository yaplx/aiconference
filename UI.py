import streamlit as st
import os
import zipfile
import io
import time
from dotenv import load_dotenv
import backend

# ==========================================
# 1. PAGE CONFIG & AUTHENTICATION
# ==========================================
st.set_page_config(page_title="Conference Desk Reviewer", page_icon="⚖️", layout="wide")
load_dotenv()

# Session State Initialization
if "processing" not in st.session_state: st.session_state.processing = False
if "results" not in st.session_state: st.session_state.results = None


def check_password():
    """Checks for password in secrets or env vars."""
    if "APP_PASSWORD" in st.secrets:
        secret_password = st.secrets["APP_PASSWORD"]
    elif os.getenv("APP_PASSWORD"):
        secret_password = os.getenv("APP_PASSWORD")
    else:
        return True  # No password set, allow access

    user_input = st.text_input("🔑 Enter Access Password", type="password")
    if user_input == secret_password:
        return True
    return False


if not check_password():
    st.stop()

# API Key Check
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
    """
    Creates a ZIP file containing all PDF reports and a summary CSV.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for item in results_list:
            pdf_name = f"Report_{item['filename']}.pdf"
            zip_file.writestr(pdf_name, item['pdf_bytes'])

        if results_list[0].get('decision') != "N/A":
            csv_data = backend.create_batch_csv(results_list)
            zip_file.writestr("Batch_Summary.csv", csv_data)

    return zip_buffer.getvalue()


# ==========================================
# 3. MAIN INTERFACE
# ==========================================
st.title("⚖️ AI Conference Reviewer")

# --- CONFERENCE SELECTION ---
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

# --- FILE UPLOAD ---
uploaded_files = st.file_uploader(
    "Upload PDF(s)",
    type="pdf",
    accept_multiple_files=True,
    disabled=st.session_state.processing
)

# --- SHOW DETAILS CHECKBOX ---
show_details = st.checkbox("Show details on screen (Enable Tabs)", value=True, disabled=st.session_state.processing)

# --- ACTION BUTTON ---
if uploaded_files and not st.session_state.processing:
    if st.button("🚀 Start AI Review"):
        st.session_state.processing = True
        st.session_state.results = []  # Clear previous results
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
            # Container for live updates
            if show_details:
                file_container = st.expander(f"📄 Processing: {uploaded_file.name}", expanded=True)
            else:
                file_container = st.empty()

            # Data structure to store section details for later reconstruction
            file_section_data = []
            first_pass_result = ""

            with file_container:
                # --- A. Extraction ---
                uploaded_file.seek(0)
                sections = backend.extract_sections_visual(uploaded_file)
                full_text_clean = backend.combine_section_content(sections)

                # Identify valid sections
                valid_sections = [s for s in sections if
                                  not any(skip in s['title'].upper() for skip in backend.SKIP_REVIEW_SECTIONS)]

                # Setup Tabs
                tab_names = ["🔍 First Pass"] + [s['title'] for s in valid_sections]

                if show_details:
                    tabs = st.tabs(tab_names)
                    first_pass_tab = tabs[0]
                    section_tabs = tabs[1:]
                else:
                    first_pass_tab = st.empty()
                    section_tabs = []

                # --- B. First Pass ---
                with first_pass_tab:
                    st.info("Analyzing Abstract & Structure...")
                    first_pass_result = backend.evaluate_first_pass(
                        client,
                        uploaded_file.name,
                        full_text_clean[:4000],
                        target_conference
                    )
                    st.markdown(first_pass_result)

                report_log = f"\n\n--- FIRST PASS ---\n{first_pass_result}\n\n"
                decision = "PROCEED"
                notes = "Standard review."

                if "REJECT" in first_pass_result:
                    decision = "REJECT"
                    report_log += "**Skipping detailed section review due to rejection.**"
                    if "REASON:" in first_pass_result:
                        notes = first_pass_result.split("REASON:")[1].strip()
                else:
                    # --- C. Second Pass ---
                    report_log += "--- SECTION ANALYSIS ---\n"
                    flagged_items = []

                    for idx, sec in enumerate(valid_sections):
                        # Use the specific tab for this section
                        current_tab = section_tabs[idx] if show_details else st.empty()

                        with current_tab:
                            with st.spinner(f"Reading..."):
                                feedback = backend.generate_section_review(
                                    client,
                                    sec['title'],
                                    sec['content'],
                                    uploaded_file.name
                                )

                            if feedback:
                                st.markdown(feedback)
                                report_log += f"\n--- SECTION: {sec['title']} ---\n{feedback}\n"

                                # Store for reconstructing UI later
                                file_section_data.append({
                                    "title": sec['title'],
                                    "content": feedback
                                })

                                if "FLAGGED ISSUES" in feedback and "(None)" not in feedback:
                                    flagged_items.append(sec['title'])

                    if flagged_items:
                        decision = "Accept w/ Suggestions"
                        notes = f"Issues in: {', '.join(flagged_items)}"
                    else:
                        decision = "Accept"

            # Generate PDF
            pdf_bytes = backend.create_pdf_report(report_log, filename=uploaded_file.name)

            # Save EVERYTHING needed to rebuild the UI
            temp_results.append({
                'filename': uploaded_file.name,
                'decision': decision,
                'notes': notes,
                'report_text': report_log,
                'pdf_bytes': pdf_bytes,
                'first_pass_data': first_pass_result,  # Saved for display
                'section_data': file_section_data  # Saved for display
            })

        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}")

        progress_bar.progress((i + 1) / len(uploaded_files))

    st.session_state.results = temp_results
    st.session_state.processing = False
    status_text.text("Processing Complete!")
    st.rerun()

# ==========================================
# 5. RESULTS & DOWNLOADS (RECONSTRUCTED UI)
# ==========================================
if st.session_state.results:
    st.divider()
    st.header("📥 Reviews Completed")

    results = st.session_state.results

    # --- BATCH DOWNLOAD ---
    if len(results) > 1:
        st.info("📦 **Batch Download Available**")
        zip_data = create_zip_of_reports(results)
        st.download_button(
            label=f"⬇️ Download All {len(results)} Reports (.zip)",
            data=zip_data,
            file_name="Conference_Reviews_Batch.zip",
            mime="application/zip",
            type="primary"
        )
        st.divider()

    # --- REBUILD DETAILED UI FOR EACH FILE ---
    for res in results:
        # Create the main container (Expander)
        # We put the decision in the title so it's visible immediately
        icon = "✅" if res['decision'] == "Accept" else "⚠️" if "Suggestions" in res['decision'] else "❌"

        with st.expander(f"{icon} {res['filename']}  |  Decision: {res['decision']}", expanded=True):

            # 1. PROMINENT DOWNLOAD BUTTON
            col1, col2 = st.columns([1, 4])
            with col1:
                st.download_button(
                    label="⬇️ Download PDF Report",
                    data=res['pdf_bytes'],
                    file_name=f"Report_{res['filename']}.pdf",
                    mime="application/pdf",
                    type="primary"  # Makes it stand out
                )
            with col2:
                if res['notes']:
                    st.info(f"**Summary Notes:** {res['notes']}")

            st.divider()

            # 2. RECONSTRUCT TABS (If detail data exists)
            # This ensures the screen "stays" exactly as it looked during processing

            # Collect valid section titles from saved data
            saved_sections = res.get('section_data', [])
            tab_titles = ["🔍 First Pass"] + [s['title'] for s in saved_sections]

            if tab_titles:
                result_tabs = st.tabs(tab_titles)

                # Fill First Pass Tab
                with result_tabs[0]:
                    st.markdown(res.get('first_pass_data', "No data."))

                # Fill Section Tabs
                for i, sec_data in enumerate(saved_sections):
                    # tab index is i+1 because 0 is First Pass
                    with result_tabs[i + 1]:
                        st.markdown(sec_data['content'])
            else:
                # Fallback if no detailed data (e.g. error or immediate reject)
                st.text_area("Full Log", res['report_text'], height=200)

    # New Review Button
    st.divider()
    if st.button("Start New Review"):
        st.session_state.results = None
        st.rerun()