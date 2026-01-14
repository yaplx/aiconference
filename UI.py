import streamlit as st
import os
import zipfile
import io
from dotenv import load_dotenv
import backend

# ==========================================
# 1. PAGE CONFIG & AUTHENTICATION
# ==========================================
st.set_page_config(page_title="Conference Desk Reviewer", page_icon="⚖️")
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

    # Original UI: Input in main area
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
            # Add PDF report
            pdf_name = f"Report_{item['filename']}.pdf"
            zip_file.writestr(pdf_name, item['pdf_bytes'])

        # Add Summary CSV if available
        if results_list[0].get('decision') != "N/A":
            csv_data = backend.create_batch_csv(results_list)
            zip_file.writestr("Batch_Summary.csv", csv_data)

    return zip_buffer.getvalue()


# ==========================================
# 3. MAIN INTERFACE
# ==========================================
st.title("⚖️ AI Conference Reviewer")

# --- CONFERENCE SELECTION (Main Area) ---
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

# --- FILE UPLOAD (Main Area) ---
uploaded_files = st.file_uploader(
    "Upload PDF(s)",
    type="pdf",
    accept_multiple_files=True,
    disabled=st.session_state.processing
)

# --- SHOW DETAILS CHECKBOX ---
show_details = st.checkbox("Show details on screen", value=True, disabled=st.session_state.processing)

# --- ACTION BUTTON (Main Area) ---
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
            # Reset file pointer
            uploaded_file.seek(0)

            # --- AI ANALYSIS ---

            # 1. Extract Sections
            sections = backend.extract_sections_visual(uploaded_file)

            # Combine text for First Pass (replacing the old debug method)
            full_text_clean = backend.combine_section_content(sections)

            # 2. First Pass (Desk Reject)
            first_pass = backend.evaluate_first_pass(
                client,
                uploaded_file.name,
                full_text_clean[:4000],
                target_conference
            )

            report_log = f"\n\n--- FIRST PASS ---\n{first_pass}\n\n"

            decision = "PROCEED"
            notes = "Standard review."

            if "REJECT" in first_pass:
                decision = "REJECT"
                report_log += "**Skipping detailed section review due to rejection.**"
                if "REASON:" in first_pass:
                    notes = first_pass.split("REASON:")[1].strip()
            else:
                # 3. Second Pass (Section Review)
                report_log += "--- SECTION ANALYSIS ---\n"
                flagged_items = []

                for sec in sections:
                    feedback = backend.generate_section_review(
                        client,
                        sec['title'],
                        sec['content'],
                        uploaded_file.name
                    )
                    if feedback:
                        report_log += f"\n--- SECTION: {sec['title']} ---\n{feedback}\n"

                        if "FLAGGED ISSUES" in feedback and "(None)" not in feedback:
                            flagged_items.append(sec['title'])

                if flagged_items:
                    decision = "Accept w/ Suggestions"
                    notes = f"Issues in: {', '.join(flagged_items)}"
                else:
                    decision = "Accept"

            report_text = report_log

            # --- GENERATE PDF ---
            pdf_bytes = backend.create_pdf_report(report_text, filename=uploaded_file.name)

            temp_results.append({
                'filename': uploaded_file.name,
                'decision': decision,
                'notes': notes,
                'report_text': report_text,
                'pdf_bytes': pdf_bytes
            })

        except Exception as e:
            st.error(f"Error processing {uploaded_file.name}: {e}")

        progress_bar.progress((i + 1) / len(uploaded_files))

    st.session_state.results = temp_results
    st.session_state.processing = False
    status_text.text("Processing Complete!")
    st.rerun()

# ==========================================
# 5. RESULTS & DOWNLOADS
# ==========================================
if st.session_state.results:
    st.divider()
    st.header("📥 Results & Downloads")

    results = st.session_state.results

    # --- BATCH DOWNLOAD (ZIP) ---
    if len(results) > 1:
        st.subheader("📦 Batch Download")
        zip_data = create_zip_of_reports(results)

        st.download_button(
            label=f"⬇️ Download All {len(results)} Reports (.zip)",
            data=zip_data,
            file_name="Conference_Reviews_Batch.zip",
            mime="application/zip",
            type="primary"
        )
        st.write("---")

    # --- INDIVIDUAL REPORTS ---
    st.subheader("📄 Individual Files")

    for res in results:
        with st.expander(f"{res['filename']} - [{res['decision']}]"):
            col_a, col_b = st.columns([1, 3])

            with col_a:
                st.download_button(
                    label="⬇️ Download PDF",
                    data=res['pdf_bytes'],
                    file_name=f"Report_{res['filename']}.pdf",
                    mime="application/pdf"
                )

            with col_b:
                st.info(f"**Notes:** {res['notes']}")

            # Text Preview (Only shows if checkbox is checked)
            if show_details:
                st.text_area("Report Content:", res['report_text'], height=250)

    # Reset Button
    if st.button("Start New Review"):
        st.session_state.results = None
        st.rerun()