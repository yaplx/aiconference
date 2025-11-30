import fitz  # PyMuPDF for PDF extraction
from openai import OpenAI

# Initialize OpenAI client
client = OpenAI(api_key="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")

# Step 1: Extract text from PDF
def extract_text_from_pdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text

# Step 2: (Optional) Split text into sections (simple version using keywords)
def split_into_sections(text):
    sections = {}
    keywords = ["Abstract", "Introduction", "Method", "Results", "Conclusion", "References"]

    for i, keyword in enumerate(keywords):
        start = text.find(keyword)
        if start != -1:
            end = text.find(keywords[i + 1], start) if i + 1 < len(keywords) else len(text)
            sections[keyword] = text[start:end].strip()

    return sections

# Step 3: Build prompt for LLM
def build_prompt(section_name, section_text):
    return f"""
You are an IEEE conference reviewer assistant. 
Read the following {section_name} section and suggest 3–5 specific improvements 
to clarity, completeness, formatting, or scientific quality. 
Do not invent data or results. 
Section text:
{section_text[:2000]}  # limit tokens for safety
"""

# Step 4: Query LLM
def query_llm(prompt):
    response = client.chat.completions.create(
        model="gpt-5",  # or another model
        messages=[{"role": "user", "content": prompt}],
        # max_tokens=50
    )
    return response.choices[0].message["content"]

# Step 5: Generate improvement report
def generate_report(sections):
    report = "=== AI-Powered Paper Improvement Report ===\n\n"
    for name, text in sections.items():
        prompt = build_prompt(name, text)
        suggestions = query_llm(prompt)
        report += f"\n## {name} Section Improvements:\n"
        report += suggestions + "\n"
    return report

# Step 6: Save report as text file (later PDF possible)
def save_report(report, filename="improvement_report.txt"):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(report)

# === Main Program ===
if __name__ == "__main__":
    pdf_path = "An_Example_Conference_Paper.pdf"   # Replace with uploaded paper
    paper_text = extract_text_from_pdf(pdf_path)
    sections = split_into_sections(paper_text)

    if not sections:
        sections = {"Full Paper": paper_text}  # fallback if no split

    report = generate_report(sections)
    save_report(report)

    print("Improvement report generated successfully!")
