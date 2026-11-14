import io

import pytest
from docx import Document
from docx.enum.text import WD_COLOR_INDEX

from app.filling.docx import (
    DocxFillError,
    FillValue,
    fill_docx,
    find_placeholders,
)


def to_bytes(document) -> bytes:
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def read(data: bytes):
    return Document(io.BytesIO(data))


def value(text: str, status: str = "filled", label: str = "Field") -> FillValue:
    return FillValue(label=label, value=text, status=status)  # type: ignore[arg-type]


def test_placeholder_in_one_run_is_replaced() -> None:
    document = Document()
    document.add_paragraph("Governing law: {{governing_law}}.")

    data, report = fill_docx(to_bytes(document), {"governing_law": value("State of Washington")})

    assert read(data).paragraphs[0].text == "Governing law: State of Washington."
    assert report.filled == ["governing_law"]


def test_placeholder_split_over_several_runs_keeps_the_text_around_it() -> None:
    # Word splits placeholders like this after spell-checking or partial formatting.
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("Law: {{gov")
    paragraph.add_run("erning_")
    bold = paragraph.add_run("law}} applies")
    bold.bold = True

    data, report = fill_docx(to_bytes(document), {"governing_law": value("Washington")})

    result = read(data).paragraphs[0]
    assert result.text == "Law: Washington applies"
    assert report.filled == ["governing_law"]


def test_value_takes_the_formatting_of_the_run_where_the_placeholder_starts() -> None:
    document = Document()
    paragraph = document.add_paragraph()
    paragraph.add_run("Term: ")
    paragraph.add_run("{{term}}").bold = True

    data, _ = fill_docx(to_bytes(document), {"term": value("one (1) year")})

    runs = read(data).paragraphs[0].runs
    filled = next(r for r in runs if r.text == "one (1) year")
    assert filled.bold is True
    assert next(r for r in runs if r.text == "Term: ").bold is None


def test_two_placeholders_in_one_run_and_the_same_key_twice() -> None:
    document = Document()
    document.add_paragraph("{{a}} and {{b}} and {{a}} again")

    data, report = fill_docx(to_bytes(document), {"a": value("1"), "b": value("2")})

    assert read(data).paragraphs[0].text == "1 and 2 and 1 again"
    assert sorted(report.filled) == ["a", "b"]  # each key is reported once


def test_spaces_inside_the_braces_are_allowed() -> None:
    document = Document()
    document.add_paragraph("Notice: {{ notice }}")

    data, _ = fill_docx(to_bytes(document), {"notice": value("10 days")})

    assert read(data).paragraphs[0].text == "Notice: 10 days"


def test_tables_headers_and_footers_are_filled() -> None:
    document = Document()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 1).text = "{{term}}"
    nested = table.cell(0, 0).add_table(rows=1, cols=1)
    nested.cell(0, 0).text = "{{term}}"
    section = document.sections[0]
    section.header.paragraphs[0].text = "Header {{term}}"
    section.footer.paragraphs[0].text = "Footer {{term}}"

    data, report = fill_docx(to_bytes(document), {"term": value("1 year")})

    result = read(data)
    assert result.tables[0].cell(0, 1).text == "1 year"
    assert result.tables[0].cell(0, 0).tables[0].cell(0, 0).text == "1 year"
    assert result.sections[0].header.paragraphs[0].text == "Header 1 year"
    assert result.sections[0].footer.paragraphs[0].text == "Footer 1 year"
    assert report.filled == ["term"]


def test_missing_value_gets_a_visible_highlighted_marker() -> None:
    document = Document()
    document.add_paragraph("Law: {{law}}")

    data, report = fill_docx(
        to_bytes(document), {"law": value("", status="missing", label="Governing law")}
    )

    paragraph = read(data).paragraphs[0]
    assert paragraph.text == "Law: [not found: Governing law]"
    marker = next(r for r in paragraph.runs if r.text.startswith("[not found"))
    assert marker.font.highlight_color == WD_COLOR_INDEX.YELLOW
    assert report.missing == ["law"]


def test_filled_field_with_an_empty_value_counts_as_missing() -> None:
    document = Document()
    document.add_paragraph("{{x}}")

    _, report = fill_docx(to_bytes(document), {"x": value("   ", status="filled", label="X")})

    assert report.missing == ["x"] and report.filled == []


def test_unverified_value_is_inserted_but_highlighted_differently() -> None:
    document = Document()
    document.add_paragraph("Non-compete: {{nc}}")

    data, report = fill_docx(to_bytes(document), {"nc": value("No", status="unverified")})

    paragraph = read(data).paragraphs[0]
    assert paragraph.text == "Non-compete: No"
    inserted = next(r for r in paragraph.runs if r.text == "No")
    assert inserted.font.highlight_color == WD_COLOR_INDEX.TURQUOISE
    assert report.unverified == ["nc"]


def test_unknown_placeholder_is_left_in_place_and_reported() -> None:
    document = Document()
    document.add_paragraph("{{known}} {{mystery}}")

    data, report = fill_docx(to_bytes(document), {"known": value("A")})

    assert read(data).paragraphs[0].text == "A {{mystery}}"
    assert report.unknown == ["mystery"]


def test_line_breaks_in_a_value_become_line_breaks_in_the_document() -> None:
    document = Document()
    document.add_paragraph("{{addr}}")

    data, _ = fill_docx(to_bytes(document), {"addr": value("Line 1\nLine 2")})

    assert read(data).paragraphs[0].text == "Line 1\nLine 2"


def test_document_without_placeholders_is_returned_unchanged_in_content() -> None:
    document = Document()
    document.add_paragraph("Nothing to fill here.")

    data, report = fill_docx(to_bytes(document), {"a": value("x")})

    assert read(data).paragraphs[0].text == "Nothing to fill here."
    assert report == type(report)()


def test_find_placeholders_lists_each_key_once_in_order() -> None:
    document = Document()
    paragraph = document.add_paragraph("{{b}} then {{a}} then {{b}} and {{c")
    paragraph.add_run("}}")

    assert find_placeholders(to_bytes(document)) == ["b", "a", "c"]


def test_a_file_that_is_not_a_docx_raises() -> None:
    with pytest.raises(DocxFillError):
        fill_docx(b"not a docx", {})


def test_the_example_docx_only_uses_fields_of_the_example_template() -> None:
    import json
    from pathlib import Path

    examples = Path(__file__).parent.parent / "examples"
    keys = {
        f["key"]
        for f in json.loads((examples / "template_contract_basics.json").read_text())["fields"]
    }
    placeholders = find_placeholders((examples / "contract_summary_template.docx").read_bytes())

    assert placeholders and set(placeholders) <= keys
