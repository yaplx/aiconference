import streamlit as st
import os
import zipfile
import io
from dotenv import load_dotenv
import backend

# === 1. PAGE CONFIG & AUTHENTICATION ===
st.set_page_config(page_title="Conference Desk Reviewer", page_icon="⚖️")
load_dotenv()

if "processing" not in st.session_state: st.session_state.processing = False
if "generated_reports" not in st.session_state: st.session_state.generated_reports = None


# --- Password & API Key Logic ---
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
    elif user_input == "":
        st.warning("Please enter password."); return False
    else:
        st.error("❌ Incorrect password"); return False


if not check_password(): st.stop()

api_key = None
if "OPENAI_API_KEY" in st.secrets:
    api_key = st.secrets["OPENAI_API_KEY"]
elif os.getenv("OPENAI_API_KEY"):
    api_key = os.getenv("OPENAI_API_KEY")

if not api_key: st.error("🚨 API Key not found!"); st.stop()
client = backend.get_openai_client(api_key)

# === 2. UI INPUTS ===
st.title("⚖️ AI Conference Reviewer")

# NEW: Optional Conference Target
# We add a default "Optional" choice.
conference_options = [
    "(Optional) General Quality Check",
    "CVPR (Computer Vision)",
    "ICRA (Robotics)",
    "NeurIPS (AI/ML)",
    "ACL (NLP)",
    "IROS (Robotics)",
    "Custom..."
]

selected_option = st.selectbox(
    "Target Conference (for Relevance Check)",
    conference_options,
    disabled=st.session_state.processing
)

# Logic to handle the selection
target_conference = "General Academic Standards"  # Default fallback

if selected_option == "Custom...":
    user_custom = st.text_input("Enter Conference Name:", disabled=st.session_state.processing)
    if user_custom.strip():
        target_conference = user_custom
elif selected_option != "(Optional) General Quality Check":
    target_conference = selected_option

uploaded_files = st.file_uploader("Upload PDF(s)", type="pdf", accept_multiple_files=True,
                                  disabled=st.session_state.processing)
show_visuals = st.checkbox("Show details on screen", value=True, disabled=st.session_state.processing)

# === 3. PROCESSING LOGIC ===
if uploaded_files and not st.session_state.processing:
    if st.button(f"Start Review Process"):
        st.session_state.processing = True
        st.session_state.generated_reports = None
        st.rerun()

if st.session_state.processing and uploaded_files:
    main_progress = st.progress(0)
    temp_reports = []

    for file_index, uploaded_file in enumerate(uploaded_files):
        main_progress.progress(file_index / len(uploaded_files))
        st.divider()
        st.subheader(f"📄 File: {uploaded_file.name}")

        # Log the conference being checked against
        report_log = f"REVIEW REPORT\nPaper: {uploaded_file.name}\nTarget Standards: {target_conference}\n\n"

        # 1. PARSE SECTIONS
        with st.spinner("Extracting Structure..."):
            sections_list = backend.extract_sections_visual(uploaded_file)
            sections_dict = {sec['title']: sec['content'] for sec in sections_list}

            # Find Abstract for First Pass
            abstract_text = ""
            if "ABSTRACT" in sections_dict:
                abstract_text = sections_dict["ABSTRACT"]
            elif len(sections_list) > 0:
                abstract_text = sections_list[0]['content']  # Fallback to first section
            else:
                abstract_text = "No text found."

        # 2. FIRST PASS: DESK REJECT CHECK
        with st.spinner(f"Running First Pass ({target_conference})..."):
            first_pass_result = backend.evaluate_first_pass(client, uploaded_file.name, abstract_text,
                                                            target_conference)
            report_log += f"--- FIRST PASS CHECK ---\n{first_pass_result}\n\n"

            # Show Result in UI
            if "REJECT" in first_pass_result:
                st.error("❌ FIRST PASS: REJECTED")
                st.write(first_pass_result)

                # Generate partial report and skip to next file
                pdf_bytes = backend.create_pdf_report(report_log)
                temp_reports.append((f"{uploaded_file.name}_REJECTED.pdf", pdf_bytes))
                continue
            else:
                st.success("✅ FIRST PASS: PROCEED")
                with st.expander("See First Pass Details"):
                    st.write(first_pass_result)

        # 3. SECOND PASS: SECTION REVIEW
        st.write("running detailed section analysis...")
        if show_visuals:
            tabs = st.tabs([k for k in sections_dict.keys()])

        for i, (name, content) in enumerate(sections_dict.items()):
            feedback = backend.generate_section_review(client, name, content, uploaded_file.name)

            report_log += f"\n--- SECTION: {name} ---\n{feedback}\n"

            if show_visuals:
                with tabs[i]:
                    st.markdown(feedback)

        # Finalize PDF
        pdf_bytes = backend.create_pdf_report(report_log)
        temp_reports.append((f"{uploaded_file.name}_REVIEW.pdf", pdf_bytes))

    main_progress.progress(1.0)
    st.success("All processing complete!")
    st.session_state.generated_reports = temp_reports
    st.session_state.processing = False
    st.rerun()

# === 4. DOWNLOADS ===
if st.session_state.generated_reports:
    st.write("---")
    st.subheader("📥 Download Reviews")

    reports = st.session_state.generated_reports
    if len(reports) == 1:
        fname, fbytes = reports[0]
        st.download_button(f"Download {fname}", fbytes, file_name=fname)
    else:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for fname, fdata in reports:
                zf.writestr(fname, fdata)
        zip_buffer.seek(0)
        st.download_button("Download All (ZIP)", zip_buffer, file_name="Reviews.zip")

    if st.button("Start New Review"):
        st.session_state.generated_reports = None
        st.rerun()