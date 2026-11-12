import re

# "1. Definitions", "2.1 Term and termination", "10 Governing law"
_NUMBERED = re.compile(r"^\d+(?:\.\d+)*\.?\s+\S")
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
    if _NUMBERED.match(line):
        # "2. Payment is due in 30 days." is a numbered sentence, not a heading.
        # Real headings rarely end with sentence punctuation.
        return not line.endswith((".", ";", ",", ":"))
    letters = [c for c in line if c.isalpha()]
    # ALL CAPS: "TERMINATION". Needs a few letters so that stray "A" or "II" do not count.
    return len(letters) >= 3 and line.isupper()
