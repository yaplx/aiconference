import document_reader
import getai
import report_generator

def combine_section_content(sections):
    return "\n".join([f"--- {s['title']} ---\n{s['content']}" for s in sections])

# This file now acts as a bridge for the UI to call these specialized modules.
extract_sections = document_reader.extract_sections_visual
evaluate_first_pass = getai.evaluate_first_pass
generate_batch_review = getai.generate_batch_review
create_pdf = report_generator.create_pdf_report
create_zip = report_generator.create_zip_of_reports