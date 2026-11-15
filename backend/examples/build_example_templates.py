"""Builds examples/agreement_summary_card.docx: a template to try the platform with.

Run from the backend directory: uv run python examples/build_example_templates.py
Its placeholders match the fields of template_contract_basics.json.
"""

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

OUTPUT = Path(__file__).with_name("agreement_summary_card.docx")


def build() -> Document:
    document = Document()
    document.add_heading("Agreement summary card", level=1)
    note = document.add_paragraph()
    run = note.add_run(
        "Prepared from the source document. Yellow = not found, turquoise = no verified quote."
    )
    run.italic = True

    document.add_heading("Key terms", level=2)
    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for label, key in [
        ("Term of the agreement", "term"),
        ("Termination notice", "termination_notice"),
        ("Governing law", "governing_law"),
    ]:
        cells = table.add_row().cells
        cells[0].text = ""
        cells[0].paragraphs[0].add_run(label).bold = True
        cells[1].text = "{{" + key + "}}"

    document.add_heading("Obligations", level=2)
    for label, key in [
        ("Confidentiality period", "confidentiality_period"),
        ("Payment terms", "payment_terms"),
        ("Liability limit", "liability_cap"),
    ]:
        item = document.add_paragraph(style="List Bullet")
        item.add_run(f"{label}: ").bold = True
        item.add_run("{{" + key + "}}")

    document.add_heading("Restrictions", level=2)
    paragraph = document.add_paragraph()
    paragraph.add_run("Non-compete clause: ").bold = True
    paragraph.add_run("{{has_non_compete}}")

    footer = document.sections[0].footer.paragraphs[0]
    footer.text = "Governing law: {{governing_law}}"
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return document


if __name__ == "__main__":
    build().save(OUTPUT)
    print(f"Saved {OUTPUT}")
