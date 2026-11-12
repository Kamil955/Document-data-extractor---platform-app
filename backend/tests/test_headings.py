import pytest

from app.parsing.headings import looks_like_heading


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
    ],
)
def test_not_headings(line: str) -> None:
    assert not looks_like_heading(line)
