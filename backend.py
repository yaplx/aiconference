import document_reader
import getai
import report_generator

# --- Bridge Functions: This is what UI.py actually "sees" ---

def get_openai_client(api_key):
    return getai.get_openai_client(api_key)

def extract_sections(uploaded_file):
    # This maps the UI's call to the visual extraction logic
    return document_reader.extract_sections_visual(uploaded_file)

def evaluate_first_pass(client, paper_title, abstract_content, conf_choice, audience):
    return getai.evaluate_first_pass(client, paper_title, abstract_content, conf_choice, audience)

def generate_batch_review(client, sections_list, paper_title, conf_choice, audience):
    return getai.generate_batch_review(client, sections_list, paper_title, conf_choice, audience)

def create_pdf(full_report, filename, audience):
    return report_generator.create_pdf_report(full_report, filename, audience)

def create_zip(results_list):
    # Fixed the naming to match UI.py's expectations
    return report_generator.create_zip_of_reports(results_list)

def combine_section_content(sections):
    return "\n".join([f"--- {s['title']} ---\n{s['content']}" for s in sections])