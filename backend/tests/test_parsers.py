import pytest

from app.core.content_types import DOCX_MIME, PDF_MIME
from app.parsing import ParseError, parse_document
from app.parsing.pdf import parse_pdf
from tests.files import make_blank_pdf, make_docx, make_pdf


def test_pdf_gives_lines_with_page_numbers() -> None:
    data = make_pdf([["1. Definitions", "Supplier means ACME."], ["2. Payment", "Pay in 30 days."]])
    blocks = parse_pdf(data)
    by_text = {b.text: b for b in blocks}
    assert by_text["Supplier means ACME."].page == 1
    assert by_text["Pay in 30 days."].page == 2
    assert by_text["1. Definitions"].is_heading
    assert not by_text["Supplier means ACME."].is_heading


def test_pdf_without_text_layer_gives_no_blocks() -> None:
    assert parse_pdf(make_blank_pdf()) == []


def test_garbage_is_a_parse_error() -> None:
    with pytest.raises(ParseError):
        parse_document(b"%PDF-1.7 but not really a pdf", PDF_MIME)
    with pytest.raises(ParseError):
        parse_document(b"PK\x03\x04 not a docx", DOCX_MIME)


def test_unsupported_type_is_a_parse_error() -> None:
    with pytest.raises(ParseError):
        parse_document(b"data", "text/plain")


def test_docx_uses_styles_for_headings_and_reads_tables_in_order() -> None:
    blocks = parse_document(make_docx(), DOCX_MIME)
    texts = [b.text for b in blocks]
    assert texts == [
        "1. Definitions",
        "In this agreement the Supplier means ACME Ltd.",
        "Item | Price",
        "Widget | 100 EUR",
        "2. Payment",
        "Payment is due within 30 days of the invoice date.",
    ]
    assert [b.is_heading for b in blocks] == [True, False, False, False, True, False]
    assert all(b.page is None for b in blocks)


def test_running_headers_and_footers_are_removed() -> None:
    from app.parsing.pdf import strip_running_lines

    pages = [
        ["Contract header", "1. Definitions", "text one", f"{n} of 5 11/12/26, 19:17"]
        for n in range(1, 6)
    ]
    pages[2][2] = "unique body text"

    cleaned = strip_running_lines(pages)

    assert cleaned[2] == ["1. Definitions", "unique body text"] or cleaned[2] == [
        "unique body text"
    ]
    assert all("of 5" not in line for lines in cleaned for line in lines)
    assert all("Contract header" not in lines for lines in cleaned)


def test_short_documents_keep_repeated_lines() -> None:
    from app.parsing.pdf import strip_running_lines

    pages = [["same line"], ["same line"], ["same line"]]
    assert strip_running_lines(pages) == pages


def test_footer_is_not_a_section_in_a_real_pdf() -> None:
    titles = ["Definitions", "Payment", "Term", "Liability", "Notices", "Governing law"]
    pages = [
        [f"{n}. {title}", "body text of the clause", f"{n} of 6"]
        for n, title in enumerate(titles, 1)
    ]
    blocks = parse_pdf(make_pdf(pages))

    assert not any("of 6" in b.text for b in blocks)
    assert [b.text for b in blocks if b.is_heading] == [
        f"{n}. {t}" for n, t in enumerate(titles, 1)
    ]


def test_page_counters_that_restart_in_an_attachment_are_removed() -> None:
    from app.parsing.pdf import strip_running_lines

    # 12 pages; pages 5-9 carry "1 Master Agreement" ... "5 Master Agreement" (5 of 12 pages:
    # below the 50% share rule, so only the page-counter rule can remove them).
    words = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima".split()
    pages = [[f"body text {word}"] for word in words]
    for n in range(5, 10):
        pages[n - 1].insert(0, f"{n - 4} [*****] Master Agreement")

    cleaned = strip_running_lines(pages)

    assert all("Master Agreement" not in line for lines in cleaned for line in lines)
    assert cleaned[4] == ["body text echo"]


def test_numbered_lines_without_a_constant_page_offset_are_kept() -> None:
    from app.parsing.pdf import strip_running_lines

    numbers = [1, 3, 2, 5, 4]  # "Article N" on 5 of 12 pages, numbers unrelated to the page
    pages = [[f"body text {chr(97 + i)}"] for i in range(12)]
    for page_index, number in enumerate(numbers):
        pages[page_index].insert(0, f"Article {number}")

    cleaned = strip_running_lines(pages)

    assert [lines[0] for lines in cleaned[:5]] == [f"Article {n}" for n in numbers]


def test_run_in_headings_become_sections_in_a_real_pdf() -> None:
    page = [
        "MUTUAL NONDISCLOSURE AGREEMENT",
        "1. Definitions. For purposes of this Agreement, the following definitions apply.",
        "2. Term. This Agreement shall remain in force for one year from the Effective Date.",
    ]
    blocks = parse_pdf(make_pdf([page]))

    assert [b.text for b in blocks if b.is_heading] == [
        "MUTUAL NONDISCLOSURE AGREEMENT",
        "1. Definitions.",
        "2. Term.",
    ]
