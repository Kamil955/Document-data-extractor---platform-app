import re

# "1. Definitions", "2.1 Term and termination", "10 Governing law".
# The first number has at most 2 digits: contracts rarely have 100+ top-level sections, while
# "252 Nassau Street" (a street address) or "2023 Annual Report" are not headings.
_NUMBERED = re.compile(r"^\d{1,2}(?:\.\d+)*\.?\s+\S")
_NUMBERED_PREFIX = re.compile(r"^\d{1,2}(?:\.\d+)*\.?\s+")
# A table-of-contents entry: "4.6.2 Provider Facilities. 10" (the title ends with a page number).
_TOC_ENTRY = re.compile(r"\s\d{1,3}$")
# "1 of 83" (page counters printed by browsers and word processors)
_PAGE_COUNTER = re.compile(r"^\d+\s+of\s+\d+\b", re.I)
# "Article 3", "Section 4.2 Payment", "Clause IV", "§ 5"
_KEYWORD = re.compile(r"^(?:article|section|clause|chapter|§)\s*[\dIVXLC]+(?:\.\d+)*\b", re.I)

_MAX_HEADING_CHARS = 80
_MAX_HEADING_WORDS = 10
_SENTENCE_END = (".", ";", ",", ":")

# Words that stay lowercase in a Title Case heading ("Fees for Services", "Time and Materials").
_MINOR_WORDS = frozenset(
    "a an the of for and or in on to by with at from under as into per".split()
)


def _is_title_case(text: str) -> bool:
    """True for "Fees for Services" or "CHARGES AND PAYMENT", false for "Payment is due".

    Contract headings are often followed by a period ("6.1 Fees for Services."), so the
    period alone cannot tell a heading from a numbered sentence. Capitalisation can: a
    sentence has many lowercase content words ("is", "due", "shall", "deliver").
    """
    words = text.split()
    if not words or len(words) > _MAX_HEADING_WORDS:
        return False
    # Only words starting with a letter count: numbers, "(a)", dashes carry no signal.
    significant = [w for w in words if w[0].isalpha() and w.lower() not in _MINOR_WORDS]
    if not significant:
        return False
    capitalised = sum(1 for w in significant if w[0].isupper())
    return capitalised / len(significant) >= 0.8


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
        # Table-of-contents lines look like headings but end with a page number; they would
        # otherwise create one tiny, useless "section" per entry.
        if line.endswith((";", ",", ":")) or _TOC_ENTRY.search(line):
            return False
        if line.endswith("."):
            # "6.1 Fees for Services." is a heading, "2. Payment is due in 30 days." is not.
            return _is_title_case(_NUMBERED_PREFIX.sub("", line).rstrip("."))
        return True
    letters = [c for c in line if c.isalpha()]
    # ALL CAPS: "TERMINATION". Needs a few letters so that stray "A" or "II" do not count.
    # A trailing period means a sentence: contracts print disclaimers in capitals, and the
    # last wrapped line of one ("...SUITABILITY FOR USE BY PROVIDER.") is not a heading.
    return (
        len(letters) >= 3
        and line.isupper()
        and not line.endswith(_SENTENCE_END)
        and len(line.split()) <= _MAX_HEADING_WORDS
    )
