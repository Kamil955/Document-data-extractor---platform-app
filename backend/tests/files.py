"""Builders for small real PDF and DOCX files used in tests."""

import io

from docx import Document as WordDocument
from fpdf import FPDF


def make_pdf(pages: list[list[str]]) -> bytes:
    """A PDF with a real text layer. `pages` is a list of pages, each a list of lines."""
    pdf = FPDF()
    pdf.set_font("Helvetica", size=11)
    for lines in pages:
        pdf.add_page()
        for line in lines:
            pdf.cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def make_blank_pdf() -> bytes:
    """A PDF page with no text at all: what a scanned document looks like to a parser."""
    pdf = FPDF()
    pdf.add_page()
    return bytes(pdf.output())


def make_docx() -> bytes:
    document = WordDocument()
    document.add_heading("1. Definitions", level=1)
    document.add_paragraph("In this agreement the Supplier means ACME Ltd.")
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Item"
    table.rows[0].cells[1].text = "Price"
    table.rows[1].cells[0].text = "Widget"
    table.rows[1].cells[1].text = "100 EUR"
    document.add_heading("2. Payment", level=1)
    document.add_paragraph("Payment is due within 30 days of the invoice date.")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
