import streamlit as st
import backend
import zipfile
import io
import pandas as pd

# ==========================================
# PAGE CONFIGURATION
# ==========================================
st.set_page_config(
    page_title="AI Conference Reviewer",
    page_icon="📑",
    layout="wide"
)

# ==========================================
# SIDEBAR: CONFIG & API KEY
# ==========================================
with st.sidebar:
    st.header("⚙️ Configuration")
    api_key = st.text_input("OpenAI API Key", type="password")

    st.divider()

    mode = st.radio(
        "Processing Mode",
        ["AI Analysis (Standard)", "Raw Sectioning Check (Debug)"],
        help="Select 'AI Analysis' for full review. Select 'Raw Sectioning' to just see how the code splits the PDF without calling GPT."
    )

    st.info("Upload your PDF(s) in the main window.")


# ==========================================
# HELPER: ZIP CREATION
# ==========================================
def create_zip_of_reports(results_list):
    """
    Takes a list of dictionaries [{'filename':..., 'pdf_bytes':...}, ...]
    and returns a ZIP file as bytes.
    """
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for item in results_list:
            # Add PDF report
            pdf_name = f"Report_{item['filename']}.pdf"
            zip_file.writestr(pdf_name, item['pdf_bytes'])

        # Add Summary CSV
        csv_data = backend.create_batch_csv(results_list)
        zip_file.writestr("Batch_Summary.csv", csv_data)

    return zip_buffer.getvalue()


# ==========================================
# MAIN INTERFACE
# ==========================================
st.title("📑 AI Paper Reviewer & Sectioner")

if not api_key:
    st.warning("⚠️ Please enter your OpenAI API Key in the sidebar to proceed.")
else:
    client = backend.get_openai_client(api_key)

    # File Uploader (Accepts Multiple)
    uploaded_files = st.file_uploader(
        "Upload Conference Papers (PDF)",
        type=["pdf"],
        accept_multiple_files=True
    )

    if uploaded_files:
        start_btn = st.button(f"Start Processing ({len(uploaded_files)} files)")

        if start_btn:
            progress_bar = st.progress(0)
            status_text = st.empty()

            results = []

            # --- PROCESSING LOOP ---
            for i, uploaded_file in enumerate(uploaded_files):
                status_text.text(f"Processing file {i + 1}/{len(uploaded_files)}: {uploaded_file.name}...")

                try:
                    # 1. READ FILE CONTENT
                    # Reset pointer just in case
                    uploaded_file.seek(0)

                    # 2. PROCESS BASED ON MODE
                    if mode == "Raw Sectioning Check (Debug)":
                        # --- DEBUG MODE (NO AI) ---
                        report_text = backend.get_raw_sectioned_text(uploaded_file)
                        decision = "N/A (Raw View)"
                        notes = "Raw sectioning output only."

                    else:
                        # --- STANDARD AI MODE ---
                        # A. Extract Sections
                        sections = backend.extract_sections_visual(uploaded_file)

                        # B. First Pass (Desk Reject)
                        # We need abstract text. Assuming abstract is in the first section or early text.
                        # For simplicity, let's grab the first 4000 chars of the whole doc for the prompt.
                        uploaded_file.seek(0)
                        full_doc_text = backend.debug_get_all_section_text(uploaded_file)  # Reuse helper to get text

                        first_pass_result = backend.evaluate_first_pass(
                            client,
                            paper_title=uploaded_file.name,
                            abstract_text=full_doc_text[:4000],
                            conference_name="General Conference"
                        )

                        full_report = f"### File: {uploaded_file.name}\n\n"
                        full_report += f"#### Pass 1: Desk Reject Check\n{first_pass_result}\n\n"

                        # Determine Decision for CSV
                        if "REJECT" in first_pass_result:
                            decision = "REJECT"
                            full_report += "**Skipping Section Review due to Reject status.**"
                        else:
                            decision = "PROCEED"
                            # C. Second Pass (Section Review)
                            full_report += "#### Pass 2: Section Analysis\n"
                            for sec in sections:
                                review = backend.generate_section_review(
                                    client,
                                    sec['title'],
                                    sec['content'],
                                    uploaded_file.name
                                )
                                if review:
                                    full_report += f"\n--- SECTION: {sec['title']} ---\n{review}\n"

                        report_text = full_report
                        notes = "AI Analysis Completed."

                    # 3. GENERATE PDF (RAM)
                    pdf_bytes = backend.create_pdf_report(report_text)

                    # 4. STORE RESULT
                    results.append({
                        'filename': uploaded_file.name,
                        'decision': decision,
                        'notes': notes,
                        'report_text': report_text,
                        'pdf_bytes': pdf_bytes
                    })

                except Exception as e:
                    st.error(f"Error processing {uploaded_file.name}: {str(e)}")

                # Update Progress
                progress_bar.progress((i + 1) / len(uploaded_files))

            status_text.text("Processing Complete!")
            st.success("All files processed.")

            # --- DISPLAY RESULTS & DOWNLOADS ---
            st.divider()

            # CASE 1: MULTIPLE FILES (BATCH)
            if len(results) > 1:
                st.subheader("📦 Batch Download")

                # 1. Summary Table
                df = pd.DataFrame(results)[['filename', 'decision', 'notes']]
                st.dataframe(df)

                # 2. ZIP Download
                zip_data = create_zip_of_reports(results)
                st.download_button(
                    label="⬇️ Download All Reports (ZIP)",
                    data=zip_data,
                    file_name="Batch_Review_Reports.zip",
                    mime="application/zip"
                )

            # CASE 2: SINGLE FILE (or View Individual in Batch)
            st.subheader("📄 Individual Reports")
            for res in results:
                with st.expander(f"Report: {res['filename']} ({res['decision']})"):
                    # Download Button for this specific PDF
                    st.download_button(
                        label=f"⬇️ Download PDF Report for {res['filename']}",
                        data=res['pdf_bytes'],
                        file_name=f"Report_{res['filename']}.pdf",
                        mime="application/pdf"
                    )

                    # Show Text Preview
                    st.text_area("Report Content Preview:", res['report_text'], height=300)