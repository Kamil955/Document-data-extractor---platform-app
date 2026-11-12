import re

# "1. Definitions", "2.1 Term and termination", "10 Governing law".
# The first number has at most 2 digits: contracts rarely have 100+ top-level sections, while
# "252 Nassau Street" (a street address) or "2023 Annual Report" are not headings.
_NUMBERED = re.compile(r"^\d{1,2}(?:\.\d+)*\.?\s+\S")
# A table-of-contents entry: "4.6.2 Provider Facilities. 10" (the title ends with a page number).
_TOC_ENTRY = re.compile(r"\s\d{1,3}$")
# "1 of 83" (page counters printed by browsers and word processors)
_PAGE_COUNTER = re.compile(r"^\d+\s+of\s+\d+\b", re.I)
# "Article 3", "Section 4.2 Payment", "Clause IV", "§ 5"
_KEYWORD = re.compile(r"^(?:article|section|clause|chapter|§)\s*[\dIVXLC]+(?:\.\d+)*\b", re.I)

_MAX_HEADING_CHARS = 80


def looks_like_heading(line: str) -> bool:
    """Guess whether a line of plain text is a section heading.

    PDFs carry no "this is a heading" information, only positioned text, so this is
    a heuristic tuned for contracts: numbered clauses, "Article N" and ALL CAPS titles.
    A wrong guess is cheap (a section is split in two), so we keep the rules simple.
    """
    line = line.strip()
    if not line or len(line) > _MAX_HEADING_CHARS:
        return False
    if _KEYWORD.match(line):
        return True
    if _PAGE_COUNTER.match(line):
        return False
    if _NUMBERED.match(line):
        # "2. Payment is due in 30 days." is a numbered sentence, not a heading.
        # Real headings rarely end with sentence punctuation.
        # Table-of-contents lines look like headings but end with a page number; they would
        # otherwise create one tiny, useless "section" per entry.
        return not line.endswith((".", ";", ",", ":")) and not _TOC_ENTRY.search(line)
    letters = [c for c in line if c.isalpha()]
    # ALL CAPS: "TERMINATION". Needs a few letters so that stray "A" or "II" do not count.
    return len(letters) >= 3 and line.isupper()
