import io
import re

import pdfplumber

from app.parsing.base import Block, ParseError
from app.parsing.headings import looks_like_heading

# Running headers and footers are only detected in documents with at least this many pages;
# in a 2-page file a line that appears twice may well be real content.
_MIN_PAGES_FOR_RUNNING_LINES = 4
# A line that (ignoring digits) appears on at least this share of the pages is a header/footer.
_RUNNING_LINE_SHARE = 0.5


def _normalize(line: str) -> str:
    # Page counters change on every page ("1 of 83", "2 of 83"), so digits are masked
    # before comparing: both lines become "# of ##".
    return re.sub(r"\d+", "#", line.lower())


def strip_running_lines(pages: list[list[str]]) -> list[list[str]]:
    """Remove page headers, footers and page numbers that repeat on most pages.

    They carry no meaning for the contract, but would end up in chunks, pollute embeddings
    and be mistaken for headings (for example "1 of 83 11/12/26, 19:17").
    """
    if len(pages) < _MIN_PAGES_FOR_RUNNING_LINES:
        return pages
    pages_with_line: dict[str, int] = {}
    for lines in pages:
        # set(): a line repeated twice on ONE page still counts as one page.
        for key in {_normalize(line) for line in lines}:
            pages_with_line[key] = pages_with_line.get(key, 0) + 1
    threshold = len(pages) * _RUNNING_LINE_SHARE
    return [
        [line for line in lines if pages_with_line[_normalize(line)] < threshold] for lines in pages
    ]


def parse_pdf(data: bytes) -> list[Block]:
    """Extract text page by page. Scanned PDFs (images only) yield no blocks: no OCR yet."""
    pages: list[list[str]] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                # extract_text() returns None for a page without a text layer.
                text = page.extract_text() or ""
                pages.append([line.strip() for line in text.splitlines() if line.strip()])
    except Exception as exc:
        # pdfplumber/pdfminer raise many unrelated exception types on malformed input
        # (their own PdfminerException, syntax errors, recursion errors, ...). The file
        # comes from a user, so any failure here means "this is not a readable PDF".
        raise ParseError(f"cannot read PDF: {exc}") from exc
    return [
        Block(line, page_number, looks_like_heading(line))
        for page_number, lines in enumerate(strip_running_lines(pages), start=1)
        for line in lines
    ]
