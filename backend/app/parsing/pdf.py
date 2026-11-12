import io

import pdfplumber

from app.parsing.base import Block, ParseError
from app.parsing.headings import looks_like_heading


def parse_pdf(data: bytes) -> list[Block]:
    """Extract text page by page. Scanned PDFs (images only) yield no blocks: no OCR yet."""
    blocks: list[Block] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page_number, page in enumerate(pdf.pages, start=1):
                # extract_text() returns None for a page without a text layer.
                text = page.extract_text() or ""
                for line in text.splitlines():
                    line = line.strip()
                    if line:
                        blocks.append(Block(line, page_number, looks_like_heading(line)))
    except Exception as exc:
        # pdfplumber/pdfminer raise many unrelated exception types on malformed input
        # (their own PdfminerException, syntax errors, recursion errors, ...). The file
        # comes from a user, so any failure here means "this is not a readable PDF".
        raise ParseError(f"cannot read PDF: {exc}") from exc
    return blocks
