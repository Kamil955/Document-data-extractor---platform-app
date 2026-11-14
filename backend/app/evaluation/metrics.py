from dataclasses import dataclass


def section_matches(section_path: str | None, expected: str) -> bool:
    """True if a chunk's section is `expected` or one of its sub-sections.

    "6.4.1 Invoices." matches "6.4.1" and "6.4", but not "6.4.10" or "6.41".
    Comparing whole numbers (not string prefixes) is what makes "16.1" differ from "16.12".
    """
    if not section_path:
        return False
    number = section_path.split()[0].rstrip(".")
    return number == expected or number.startswith(expected + ".")


# One indexed or returned chunk, reduced to what the evaluation needs: (section_path, text).
Passage = tuple[str | None, str]


def _normalize(text: str) -> str:
    # PDF line breaks and capitalisation must not decide whether a snippet is found.
    return " ".join(text.split()).casefold()


def passage_matches(
    passage: Passage, expected_sections: list[str], expected_text: list[str]
) -> bool:
    """A passage is right if it is in an expected section OR contains an expected snippet.

    Sections suit documents with numbered headings; snippets suit documents without them
    (a contract whose clauses are numbered but not titled has no usable section_path).
    """
    section, text = passage
    if any(section_matches(section, expected) for expected in expected_sections):
        return True
    haystack = _normalize(text)
    return any(_normalize(snippet) in haystack for snippet in expected_text)


def has_answer(
    indexed: list[Passage], expected_sections: list[str], expected_text: list[str] = ()
) -> bool:
    """True if the index holds at least one chunk that would count as a correct answer.

    A section whose text is empty or fully redacted produces no chunk, so a question about
    it cannot be answered and must not count as a retrieval failure.
    """
    return any(passage_matches(p, expected_sections, list(expected_text)) for p in indexed)


def first_hit_rank(
    passages: list[Passage], expected_sections: list[str], expected_text: list[str] = ()
) -> int | None:
    """1-based rank of the first correct passage in the results, or None if absent."""
    for rank, passage in enumerate(passages, start=1):
        if passage_matches(passage, expected_sections, list(expected_text)):
            return rank
    return None


@dataclass(frozen=True)
class Summary:
    questions: int
    hit_at_1: float
    hit_at_3: float
    hit_at_5: float
    mrr: float  # mean reciprocal rank: 1.0 = always first, 0.5 = typically second


def summarize(ranks: list[int | None]) -> Summary:
    n = len(ranks)

    def hit(k: int) -> float:
        return sum(1 for r in ranks if r is not None and r <= k) / n if n else 0.0

    mrr = sum(1 / r for r in ranks if r is not None) / n if n else 0.0
    return Summary(n, hit(1), hit(3), hit(5), mrr)


@dataclass(frozen=True)
class Grade:
    correct: bool
    found: bool
    supported: bool


def grade_answer(item: dict, response: dict) -> Grade:
    """Compare an /ask response with the expectation of one question.

    An item has "expected_any" (the answer must contain at least one of these snippets;
    alternatives cover paraphrases such as "ten (10) business days" / "10 business days")
    (or "expected_sections" alone, see below)
    or "expect_found": false for a question the document cannot answer: then the only
    correct behaviour is to say so instead of making something up.
    """
    found = bool(response["found"])
    expect_found = item.get("expect_found", True)
    if not expect_found:
        return Grade(not found, found, bool(response["supported"]))
    if "expected_any" not in item:
        # No known wording, only the clause the answer must come from (see "expected_sections"
        # in the retrieval sets): correct = a VERIFIED quote comes from that clause. The
        # answer text itself is not judged, so this is a proxy; read the answers for the rest.
        cited_ok = any(
            citation["verified"]
            and any(section_matches(citation["section_path"], e) for e in item["expected_sections"])
            for citation in response["citations"]
        )
        return Grade(found and cited_ok, found, bool(response["supported"]))
    answer = _normalize(response["answer"])
    contains_expected = any(_normalize(snippet) in answer for snippet in item["expected_any"])
    return Grade(found and contains_expected, found, bool(response["supported"]))
