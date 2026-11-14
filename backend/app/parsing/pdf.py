import io
import re

import pdfplumber

from app.parsing.base import Block, ParseError
from app.parsing.headings import (
    expand_run_in_headings,
    looks_like_heading,
    repair_interrupted_sentences,
)
from app.parsing.toc import strip_table_of_contents

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
    without_repeated = [
        [line for line in lines if pages_with_line[_normalize(line)] < threshold] for lines in pages
    ]
    return _drop_page_counters(without_repeated)


# Page counters that restart in an attachment ("1 Company Agreement", "2 Company Agreement")
# appear on fewer pages than the share rule needs, but their number grows with the page.
_MIN_COUNTER_PAGES = 4
_FIRST_NUMBER = re.compile(r"\d+")


def _drop_page_counters(pages: list[list[str]]) -> list[list[str]]:
    """Remove lines whose first number equals the page index plus a constant.

    "3 Master Agreement" on page 7 and "4 Master Agreement" on page 8 have the same offset
    (number - page = -4): that is a page counter, whatever number the first page started at.
    Ordinary repeated content ("Article 1", "Article 3") does not keep a constant offset.
    """

    def offset(line: str, page_index: int) -> int | None:
        match = _FIRST_NUMBER.search(line)
        return int(match.group()) - page_index if match else None

    pages_per_counter: dict[tuple[str, int], set[int]] = {}
    for page_index, lines in enumerate(pages, start=1):
        for line in lines:
            line_offset = offset(line, page_index)
            if line_offset is not None:
                pages_per_counter.setdefault((_normalize(line), line_offset), set()).add(page_index)
    counters = {
        key for key, found_on in pages_per_counter.items() if len(found_on) >= _MIN_COUNTER_PAGES
    }

    def is_counter(line: str, page_index: int) -> bool:
        line_offset = offset(line, page_index)
        return line_offset is not None and (_normalize(line), line_offset) in counters

    return [
        [line for line in lines if not is_counter(line, page_index)]
        for page_index, lines in enumerate(pages, start=1)
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
    blocks = [
        Block(line, page_number, looks_like_heading(line))
        for page_number, lines in enumerate(strip_running_lines(pages), start=1)
        for line in lines
    ]
    # Order matters: table-of-contents entries must be removed before run-in headings are split,
    # because "4.14 No Exclusivity. 12" would otherwise be taken apart and no longer recognised.
    return expand_run_in_headings(repair_interrupted_sentences(strip_table_of_contents(blocks)))
