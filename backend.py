import document_reader
import getai
import report_generator

# This allows UI.py to call backend.extract_sections() etc.
extract_sections = document_reader.extract_sections_visual
evaluate_first_pass = getai.evaluate_first_pass
generate_batch_review = getai.generate_batch_review
create_pdf = report_generator.create_pdf_report
create_zip = report_generator.create_zip_of_reports

def combine_section_content(sections):
    return "\n".join([f"--- {s['title']} ---\n{s['content']}" for s in sections])

def get_openai_client(api_key):
    return getai.get_openai_client(api_key)