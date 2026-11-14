import pytest

from app.parsing.base import Block
from app.parsing.headings import (
    expand_run_in_headings,
    looks_like_heading,
    repair_interrupted_sentences,
    split_run_in_heading,
)


@pytest.mark.parametrize(
    "line",
    [
        "1. Definitions",
        "2.1 Term and termination",
        "10 Governing law",
        "Article 3",
        "Section 4.2 Fees",
        "§ 5 Confidentiality",
        "TERMINATION",
        "Clause IV",
        "6.1 Fees for Services.",  # headings may end with a period
        "6.1.1 Time and Materials.",
        "16.12 Governing law; Venue.",  # mixed case is normal in headings
        "6. CHARGES AND PAYMENT.",
    ],
)
def test_headings(line: str) -> None:
    assert looks_like_heading(line)


@pytest.mark.parametrize(
    "line",
    [
        "",
        "12",  # a bare page number
        "Page 3 of 10",
        "2. Payment is due within 30 days.",  # numbered sentence
        "The Supplier shall deliver the goods.",
        "A",
        "II",
        "x" * 200,
        "1 of 83 11/12/26, 19:17",  # page counter from a browser print
        "4.6.2 Provider Facilities. 10",  # table-of-contents entry
        "252 Nassau Street",  # street address
        "SUITABILITY FOR USE BY PROVIDER.",  # last line of an ALL CAPS disclaimer sentence
        "2. The Supplier shall deliver the goods.",
    ],
)
def test_not_headings(line: str) -> None:
    assert not looks_like_heading(line)


def test_run_in_heading_is_split_from_the_clause_text() -> None:
    line = "1. Definitions. For purposes of this Agreement, the following definitions apply:"
    assert split_run_in_heading(line) == (
        "1. Definitions.",
        "For purposes of this Agreement, the following definitions apply:",
    )
    long_title = "6. Term and Termination; Termination of Obligation. This Agreement shall begin on"
    assert split_run_in_heading(long_title) == (
        "6. Term and Termination; Termination of Obligation.",
        "This Agreement shall begin on",
    )


@pytest.mark.parametrize(
    "line",
    [
        "2. Payment is due. Late fees apply after thirty days.",  # a numbered sentence
        "4.14 No Exclusivity. 12",  # table-of-contents entry
        "Definitions. For purposes of this Agreement",  # no number
        "3. Fees",  # nothing follows
    ],
)
def test_not_run_in_headings(line: str) -> None:
    assert split_run_in_heading(line) is None


def test_expand_run_in_headings() -> None:
    blocks = [Block("1. Definitions. For purposes of this Agreement:", 1), Block("plain text", 1)]

    assert expand_run_in_headings(blocks) == [
        Block("1. Definitions.", 1, True),
        Block("For purposes of this Agreement:", 1, False),
        Block("plain text", 1, False),
    ]


def _body(text: str, page: int = 1) -> Block:
    return Block(text, page, False)


def test_watermark_inside_a_sentence_is_dropped_and_the_sentence_stays_whole():
    blocks = [
        Block("4. Identification of Confidential Information.", 1, True),
        _body("Information disclosed in oral form will be identified as"),
        Block("SAMPLE-NOTINTENDEDFORSIGNATURE2", 2, True),
        _body("such by the Disclosing Party in writing within thirty (30) days.", 2),
    ]

    result = repair_interrupted_sentences(blocks)

    assert [b.text for b in result] == [
        "4. Identification of Confidential Information.",
        "Information disclosed in oral form will be identified as",
        "such by the Disclosing Party in writing within thirty (30) days.",
    ]
    assert [b.is_heading for b in result] == [True, False, False]


def test_heading_after_a_finished_sentence_is_kept():
    blocks = [
        _body("The Agreement ends on that date."),
        Block("TERMINATION", 1, True),
        _body("either party may terminate it with notice."),
    ]

    assert repair_interrupted_sentences(blocks) == blocks


def test_interrupting_line_with_lowercase_is_kept_as_body_text():
    blocks = [
        _body("The fees are described in"),
        Block("5. Fees and Payment", 1, True),
        _body("and are payable monthly."),
    ]

    result = repair_interrupted_sentences(blocks)

    assert [b.text for b in result] == [b.text for b in blocks]
    assert not any(b.is_heading for b in result)
