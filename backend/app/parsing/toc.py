import re

from app.parsing.base import Block

# "4.14 No Exclusivity. 12", "5. PERFORMANCE STANDARDS. 12", "Fees ........ 14"
_SECTION_START = re.compile(r"^\d{1,2}(?:\.\d+)*\.?\s+\S")
_DOT_LEADERS = re.compile(r"\.{3,}")
_TRAILING_PAGE = re.compile(r"(?:\s|\.)(\d{1,3})$")

# Fewer consecutive entries than this are more likely a few numbered lines that happen to end
# with a number ("3. Payment within 30") than a table of contents.
_MIN_ENTRIES = 6


def _page_of_entry(text: str) -> int | None:
    """The page number a table-of-contents entry points to, or None if it is not an entry."""
    match = _TRAILING_PAGE.search(text)
    if match is None or not (_SECTION_START.match(text) or _DOT_LEADERS.search(text)):
        return None
    return int(match.group(1))


def strip_table_of_contents(blocks: list[Block]) -> list[Block]:
    """Drop runs of table-of-contents entries.

    A table of contents repeats every section title of the document. In a semantic search it
    matches almost any question about any section, so it would outrank the real clauses.
    It is recognised by its shape, not by words (so it works in any language): many
    consecutive lines that start with a section number (or end with dot leaders), end with a
    page number, and whose page numbers never go down.
    """
    keep = [True] * len(blocks)
    run: list[int] = []
    last_page = 0

    def close_run() -> None:
        if len(run) >= _MIN_ENTRIES:
            for index in run:
                keep[index] = False
        run.clear()

    for index, block in enumerate(blocks):
        page = _page_of_entry(block.text)
        if page is None or page < last_page:
            close_run()
            last_page = 0
            # The entry that broke the run (page went down) may start the next one.
            page = _page_of_entry(block.text)
        if page is None:
            continue
        run.append(index)
        last_page = page
    close_run()
    return [block for block, kept in zip(blocks, keep, strict=True) if kept]
