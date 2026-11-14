import re

from app.parsing.base import Block

# "1. Definitions", "2.1 Term and termination", "10 Governing law".
# The first number has at most 2 digits: contracts rarely have 100+ top-level sections, while
# "252 Nassau Street" (a street address) or "2023 Annual Report" are not headings.
_NUMBERED = re.compile(r"^\d{1,2}(?:\.\d+)*\.?\s+\S")
_NUMBERED_PREFIX = re.compile(r"^\d{1,2}(?:\.\d+)*\.?\s+")
# A table-of-contents entry: "4.6.2 Provider Facilities. 10" (the title ends with a page number).
_TOC_ENTRY = re.compile(r"\s\d{1,3}$")
# "1 of 83" (page counters printed by browsers and word processors)
_PAGE_COUNTER = re.compile(r"^\d+\s+of\s+\d+\b", re.I)
# "Article 3", "Section 4.2 Payment", "Clause IV", "§ 5", "Artykuł 3", "Rozdział IV", "Art. 5".
# To support another language, add its words here.
_KEYWORD = re.compile(
    r"^(?:article|section|clause|chapter|artykuł|rozdział|paragraf|klauzula|sekcja|art\.|§)"
    r"\s*[\dIVXLC]+(?:\.\d+)*\b",
    re.I,
)

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
    # 0.6, not higher: real headings mix cases ("Governing law; Venue"), while sentences
    # score far lower ("Payment is due within 30 days" = 0.25).
    return capitalised / len(significant) >= 0.6


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


# "1. Definitions. For purposes of this Agreement ..." - a short title and the first sentence
# of the clause share one line (a "run-in heading", very common in contracts).
_RUN_IN = re.compile(
    r"^(?P<number>\d{1,2}(?:\.\d+)*\.?)\s+(?P<title>[A-Z][^.]{1,80}\.)\s+"
    r"(?P<body>[A-Z\u201c\"(\d].{9,})$"
)


def split_run_in_heading(line: str) -> tuple[str, str] | None:
    """Split "1. Definitions. For purposes..." into ("1. Definitions.", "For purposes...").

    Only a title that looks like a title qualifies ("Fees for Services", not "Payment is
    due"), and the rest must be long enough to be text: otherwise the line would be a
    table-of-contents entry ("4.14 No Exclusivity. 12") that merely ends with a page number.
    """
    match = _RUN_IN.match(line.strip())
    if match is None or not _is_title_case(match["title"].rstrip(".")):
        return None
    return f"{match['number']} {match['title']}", match["body"]


def expand_run_in_headings(blocks: list[Block]) -> list[Block]:
    """Replace each run-in heading line by a heading block plus a body block."""
    expanded: list[Block] = []
    for block in blocks:
        parts = None if block.is_heading else split_run_in_heading(block.text)
        if parts is None:
            expanded.append(block)
        else:
            heading, body = parts
            expanded.append(Block(heading, block.page, True))
            expanded.append(Block(body, block.page, False))
    return expanded


_SENTENCE_FINAL = ".;:!?"
_CLOSING_CHARS = ")]\"'”’"


def _ends_sentence(text: str) -> bool:
    return text.rstrip().rstrip(_CLOSING_CHARS).endswith(tuple(_SENTENCE_FINAL))


def repair_interrupted_sentences(blocks: list[Block]) -> list[Block]:
    """Handle a "heading" that sits in the middle of a sentence.

    A real heading starts new text. If the line before it has no sentence ending and the
    line after it starts in lowercase, the heading cuts one sentence in two, so it cannot
    be a heading. The typical cause is a watermark or stamp ("SAMPLE - NOT FOR SIGNATURE")
    printed on a page: the sentence runs across the page break and the watermark text lands
    in between. Treating it as a heading would split the section in two and leave the end of
    the sentence (often the answer: "... within thirty (30) days") under a wrong title.

    The line is dropped when it has no lowercase letters and no leading number (a stamp is
    noise); otherwise it is kept as body text, because it may be a real part of the sentence.
    """
    result: list[Block] = []
    for index, block in enumerate(blocks):
        following = blocks[index + 1] if index + 1 < len(blocks) else None
        previous = result[-1] if result else None
        interrupts = (
            block.is_heading
            and previous is not None
            and not previous.is_heading
            and not _ends_sentence(previous.text)
            and following is not None
            and not following.is_heading
            and following.text[:1].islower()
        )
        if not interrupts:
            result.append(block)
        elif not any(c.islower() for c in block.text) and not block.text[:1].isdigit():
            continue  # stamp-like line: noise
        else:
            result.append(Block(block.text, block.page, False))
    return result
