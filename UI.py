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
if "csv_string" not in st.session_state: st.session_state.csv_string = None


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
    else:
        return False


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

conference_options = [
    "(Optional) General Quality Check",
    "CVPR (Computer Vision)",
    "ICRA (Robotics)",
    "NeurIPS (AI/ML)",
    "ACL (NLP)",
    "IROS (Robotics)",
    "Custom..."
]
selected_option = st.selectbox("Target Conference", conference_options, disabled=st.session_state.processing)

target_conference = "General Academic Standards"
if selected_option == "Custom...":
    user_custom = st.text_input("Enter Conference Name:", disabled=st.session_state.processing)
    if user_custom.strip(): target_conference = user_custom
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
        st.session_state.csv_string = None
        st.rerun()

if st.session_state.processing and uploaded_files:
    main_progress = st.progress(0)
    temp_reports = []

    # Container for CSV Data (passed to backend later)
    batch_results_data = []

    for file_index, uploaded_file in enumerate(uploaded_files):
        main_progress.progress(file_index / len(uploaded_files))
        st.divider()
        st.subheader(f"📄 File: {uploaded_file.name}")

        report_log = f"REVIEW REPORT\nPaper: {uploaded_file.name}\nTarget: {target_conference}\n\n"

        # 1. PARSE
        with st.spinner("Extracting Structure..."):
            sections_list = backend.extract_sections_visual(uploaded_file)
            sections_dict = {sec['title']: sec['content'] for sec in sections_list}
            abstract_text = sections_dict.get("ABSTRACT", sections_list[0]['content'] if sections_list else "")

        # 2. FIRST PASS
        is_rejected = False
        with st.spinner(f"First Pass ({target_conference})..."):
            first_pass = backend.evaluate_first_pass(client, uploaded_file.name, abstract_text, target_conference)
            report_log += f"--- FIRST PASS ---\n{first_pass}\n\n"

            if "REJECT" in first_pass:
                is_rejected = True
                st.error("❌ REJECTED")
                st.write(first_pass)

                # CSV DATA (RED)
                reason = first_pass.split("REASON:")[1].strip() if "REASON:" in first_pass else "First Pass Reject"
                batch_results_data.append({
                    "filename": uploaded_file.name,
                    "decision": "REJECT",
                    "color": "RED",
                    "notes": reason
                })

            else:
                st.success("✅ PROCEED")
                with st.expander("Details"):
                    st.write(first_pass)

        # 3. SECOND PASS (If Proceed)
        if not is_rejected:
            st.write("Analyzing sections...")
            if show_visuals: tabs = st.tabs([k for k in sections_dict.keys()])

            paper_suggestions = []

            for i, (name, content) in enumerate(sections_dict.items()):
                feedback = backend.generate_section_review(client, name, content, uploaded_file.name)
                report_log += f"\n--- SECTION: {name} ---\n{feedback}\n"

                if "ACCEPT WITH SUGGESTIONS" in feedback:
                    if "**FLAGGED ISSUES (If any):**" in feedback:
                        raw = feedback.split("**FLAGGED ISSUES (If any):**")[1]
                        clean = raw.split("\n\n")[0].strip()
                        if clean and clean != "(None)":
                            paper_suggestions.append(f"[{name}]: {clean}")

                if show_visuals:
                    with tabs[i]: st.markdown(feedback)

            # CSV DATA (YELLOW vs GREEN)
            if paper_suggestions:
                combined_notes = "; ".join(paper_suggestions).replace("\n", " ")
                batch_results_data.append({
                    "filename": uploaded_file.name,
                    "decision": "PROCEED (With Suggestions)",
                    "color": "YELLOW",
                    "notes": combined_notes
                })
            else:
                batch_results_data.append({
                    "filename": uploaded_file.name,
                    "decision": "PROCEED (Clean)",
                    "color": "GREEN",
                    "notes": "No major issues."
                })

        # Generate PDF
        pdf_bytes = backend.create_pdf_report(report_log)
        fname_suffix = "REJECTED" if is_rejected else "REVIEW"
        temp_reports.append((f"{uploaded_file.name}_{fname_suffix}.pdf", pdf_bytes))

    # --- FINAL: GENERATE CSV VIA BACKEND ---
    if len(uploaded_files) > 1:
        st.session_state.csv_string = backend.create_batch_csv(batch_results_data)

    main_progress.progress(1.0)
    st.success("Complete!")
    st.session_state.generated_reports = temp_reports
    st.session_state.processing = False
    st.rerun()

# === 4. DOWNLOADS ===
if st.session_state.generated_reports:
    st.write("---")
    st.subheader("📥 Downloads")

    # CSV Download
    if st.session_state.csv_string:
        st.download_button(
            "📊 Download Batch Summary (CSV)",
            st.session_state.csv_string,
            "EasyChair_Summary.csv",
            "text/csv"
        )

    # PDF Download
    reports = st.session_state.generated_reports
    if len(reports) == 1:
        f, b = reports[0]
        st.download_button(f"Download PDF ({f})", b, f)
    else:
        z_buf = io.BytesIO()
        with zipfile.ZipFile(z_buf, "w") as zf:
            for f, b in reports: zf.writestr(f, b)
        z_buf.seek(0)
        st.download_button("📦 Download All PDFs (ZIP)", z_buf, "Reviews.zip", "application/zip")

    if st.button("New Review"):
        st.session_state.generated_reports = None
        st.session_state.csv_string = None
        st.rerun()