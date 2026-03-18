import streamlit as st
import os
import backend
import re
import headers_map as hm
from dotenv import load_dotenv
from conference_options import CONFERENCE_OPTIONS

# ==========================================
# 1. PAGE CONFIG & AUTHENTICATION
# ==========================================
st.set_page_config(page_title="AI Conference Assistant", page_icon="⚖️", layout="wide")
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
    st.error("Missing OpenAI API Key.")
    st.stop()

# ==========================================
# 2. SIDEBAR CONFIGURATION
# ==========================================
with st.sidebar:
    st.title("⚙️ Settings")
    audience = st.radio("Target Audience", ["Reviewer", "Author"], help="Changes the tone and disclaimer.")
    conf_choice = st.selectbox("Conference/Track", CONFERENCE_OPTIONS)

    st.divider()
    st.subheader("📁 Batch Upload")
    uploaded_files = st.file_uploader("Upload PDF Manuscripts", type="pdf", accept_multiple_files=True)

    process_btn = st.button("🚀 Start Desk Review", type="primary", use_container_width=True,
                            disabled=not uploaded_files)

# ==========================================
# 3. CORE PROCESSING LOGIC
# ==========================================
if process_btn and uploaded_files:
    st.session_state.processing = True
    st.session_state.results = []

    client = backend.get_openai_client(api_key)

    for uploaded_file in uploaded_files:
        with st.status(f"Processing: {uploaded_file.name}...", expanded=True) as status:
            # 1. Extraction (via document_reader)
            sections = backend.extract_sections(uploaded_file)

            # 2. Extract Title & Abstract for First Pass
            paper_title = sections[0]['content'][:200].strip() if sections else "Unknown Title"
            abstract_content = next((s['content'] for s in sections if "ABSTRACT" in s['title'].upper()),
                                    "Abstract not found.")

            # 3. First Pass Assessment
            st.write("🔍 Performing First Pass...")
            first_pass_report = backend.evaluate_first_pass(client, paper_title, abstract_content, conf_choice,
                                                            audience.lower())

            # 4. Filter Sections for Detailed Review (Skip Front/Back Matter)
            reviewable_sections = []
            for s in sections:
                clean_t = re.sub(r"^[\d\w]+\.\s*", "", s['title'].upper().strip())
                mapped = hm.HEADER_MAP.get(clean_t, clean_t)
                if mapped not in hm.FRONT_MATTER and mapped not in hm.BACK_MATTER:
                    reviewable_sections.append(s)

            # 5. Detailed Batch Review
            st.write("🧠 Generating Detailed Feedback...")
            batch_feedback = backend.generate_batch_review(client, reviewable_sections, paper_title, conf_choice,
                                                           audience.lower())

            # 6. Assemble Full Report Text
            full_report = f"TITLE: {paper_title}\n\nFIRST PASS ASSESSMENT:\n{first_pass_report}\n\n"
            for s in reviewable_sections:
                full_report += f"--- SECTION: {s['title']} ---\n{batch_feedback.get(s['title'], 'No feedback.')}\n\n"

            # 7. Generate PDF
            pdf_bytes = backend.create_pdf(full_report, uploaded_file.name, audience.lower())

            # Store results
            st.session_state.results.append({
                "filename": uploaded_file.name,
                "decision": "Accepted/Reviewable" if "ACCEPT" in first_pass_report.upper() else "Desk Reject/Revisions",
                "pdf_bytes": pdf_bytes,
                "first_pass_content": first_pass_report,
                "saved_tabs_data": [{"title": s['title'], "content": batch_feedback.get(s['title'], "")} for s in
                                    reviewable_sections],
                "audience": audience
            })
            status.update(label=f"✅ Finished: {uploaded_file.name}", state="complete")

    st.session_state.processing = False

# ==========================================
# 4. RESULTS DISPLAY
# ==========================================
if st.session_state.results:
    st.header("📋 Review Summary")

    # Batch Download
    zip_bytes = backend.create_zip(st.session_state.results)
    st.download_button("📦 Download All Reports (ZIP)", zip_bytes, "Review_Batch.zip", "application/zip")

    for res in st.session_state.results:
        icon = "✅" if "Accept" in res['decision'] else "❌"
        with st.expander(f"{icon} {res['filename']} | {res['decision']}"):
            c1, c2 = st.columns([1, 4])
            with c1:
                st.download_button(f"⬇️ Download PDF", res['pdf_bytes'], f"Report_{res['filename']}.pdf",
                                   "application/pdf")

            with c2:
                # Tabbed View: First Pass + Filtered Main Sections
                tab_titles = ["🔍 First Pass"] + [s['title'] for s in res['saved_tabs_data']]
                ui_tabs = st.tabs(tab_titles)

                with ui_tabs[0]:
                    st.markdown(res['first_pass_content'])

                for i, sec_data in enumerate(res['saved_tabs_data']):
                    with ui_tabs[i + 1]:
                        st.markdown(sec_data['content'])