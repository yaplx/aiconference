import csv
import io
import zipfile
from fpdf import FPDF
from configurator import sanitize_text_for_pdf
from disclaimer import DISCLAIMERS


def create_pdf_report(full_report_text, filename, audience):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    title = "AI Desk Review" if audience == "reviewer" else "AI Author Feedback"
    pdf.cell(0, 10, txt=title, ln=True, align='C')
    pdf.set_font("Arial", '', 8)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 4, txt=DISCLAIMERS[audience])
    pdf.ln(5)
    pdf.set_font("Arial", '', 12)
    pdf.set_text_color(0, 0, 0)

    clean_text = sanitize_text_for_pdf(full_report_text)
    for line in clean_text.split('\n'):
        line = line.encode('latin-1', 'replace').decode('latin-1')
        if "SECTION:" in line:
            pdf.ln(3)
            pdf.set_font("Arial", 'B', 12)
            pdf.cell(0, 10, txt=line, ln=True)
            pdf.set_font("Arial", '', 12)
        else:
            pdf.multi_cell(0, 5, line)
    return pdf.output(dest="S").encode("latin-1", "replace")


def create_batch_csv(results_list):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Filename", "Decision", "Comments"])
    for p in results_list:
        writer.writerow([p['filename'], p['decision'], p['notes']])
    return output.getvalue()


def create_zip_of_reports(results_list):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for item in results_list:
            pdf_name = f"Report_{item.get('audience', 'Reviewer').title()}_{item['filename']}.pdf"
            zip_file.writestr(pdf_name, item['pdf_bytes'])
        if results_list:
            zip_file.writestr("Batch_Summary.csv", create_batch_csv(results_list))
    return zip_buffer.getvalue()