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
