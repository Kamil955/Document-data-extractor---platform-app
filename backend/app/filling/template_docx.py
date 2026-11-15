"""Working with the Word document of a template: a preview for the screen and a starter file."""

import io
from collections.abc import Iterable, Iterator

from docx import Document as new_docx
from docx.document import Document as DocxDocument
from docx.table import Table, _Cell
from docx.text.hyperlink import Hyperlink
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from app.filling.docx import PLACEHOLDER, DocxFillError, _open, find_placeholders
from app.schemas import (
    PlaceholderInfo,
    PreviewParagraph,
    PreviewSegment,
    PreviewTable,
    TemplatePreview,
)

# A preview is for looking, not for reading a 300-page document: cut it short.
MAX_BLOCKS = 400


def preview_docx(data: bytes, field_keys: Iterable[str]) -> TemplatePreview:
    """The structure and text of a DOCX as plain data, with its {{placeholders}} marked.

    The browser draws this itself (headings, bold, tables, placeholder chips). It is not
    converted to HTML on the server on purpose: text from a user's file never becomes markup,
    so there is nothing to sanitize and no way to smuggle a script into the page.
    """
    document = _open(data)
    known = set(field_keys)

    blocks = []
    truncated = False
    for block in _iter_blocks(document):
        if len(blocks) >= MAX_BLOCKS:
            truncated = True
            break
        blocks.append(_table_block(block) if isinstance(block, Table) else _paragraph_block(block))

    used = find_placeholders(data)  # also covers headers and footers, which are not drawn
    return TemplatePreview(
        blocks=blocks,
        placeholders=[PlaceholderInfo(key=key, known=key in known) for key in used],
        unused_fields=[key for key in known if key not in used],
        truncated=truncated,
    )


def _iter_blocks(container: DocxDocument | _Cell) -> Iterator[Paragraph | Table]:
    # iter_inner_content keeps the real order of paragraphs and tables; the separate
    # .paragraphs and .tables lists would lose it.
    yield from container.iter_inner_content()


def _table_block(table: Table) -> PreviewTable:
    rows = []
    for row in table.rows:
        cells = []
        seen = []  # a merged cell appears once per column it spans: keep the first one only
        for cell in row.cells:
            if any(cell._tc is other for other in seen):
                continue
            seen.append(cell._tc)
            cells.append(list(_cell_paragraphs(cell)))
        rows.append(cells)
    return PreviewTable(rows=rows)


def _cell_paragraphs(cell: _Cell) -> Iterator[PreviewParagraph]:
    for block in _iter_blocks(cell):
        if isinstance(block, Table):
            for row in block.rows:
                for inner in row.cells:
                    yield from _cell_paragraphs(inner)
        else:
            yield _paragraph_block(block)


def _runs(paragraph: Paragraph) -> Iterator[Run]:
    for item in paragraph.iter_inner_content():
        if isinstance(item, Hyperlink):
            yield from item.runs
        else:
            yield item


def _paragraph_block(paragraph: Paragraph) -> PreviewParagraph:
    # One entry per character: (character, bold, italic, underline). Placeholders are found
    # on the text of the whole paragraph, because Word may split "{{key}}" over several runs.
    chars: list[tuple[str, bool, bool, bool]] = []
    for run in _runs(paragraph):
        style = (bool(run.bold), bool(run.italic), bool(run.underline))
        chars.extend((char, *style) for char in run.text)
    text = "".join(c[0] for c in chars)

    segments: list[PreviewSegment] = []

    def add_text(start: int, end: int) -> None:
        # Consecutive characters with the same formatting become one segment.
        group_start = start
        for i in range(start + 1, end + 1):
            if i == end or chars[i][1:] != chars[group_start][1:]:
                _, bold, italic, underline = chars[group_start]
                segments.append(
                    PreviewSegment(
                        text=text[group_start:i], bold=bold, italic=italic, underline=underline
                    )
                )
                group_start = i

    position = 0
    for match in PLACEHOLDER.finditer(text):
        if match.start() > position:
            add_text(position, match.start())
        _, bold, italic, underline = chars[match.start()]
        segments.append(
            PreviewSegment(
                text=match[0], key=match[1], bold=bold, italic=italic, underline=underline
            )
        )
        position = match.end()
    if position < len(text):
        add_text(position, len(text))

    return PreviewParagraph(
        style=_style_of(paragraph), level=_level_of(paragraph), segments=segments
    )


def _style_of(paragraph: Paragraph) -> str:
    name = (paragraph.style.name if paragraph.style is not None else "") or ""
    if name == "Title":
        return "title"
    if name.startswith("Heading"):
        return "heading"
    # A list item is either in a "List ..." style or has a numbering property of its own.
    properties = paragraph._p.pPr
    if name.startswith("List") or (properties is not None and properties.numPr is not None):
        return "list"
    return "normal"


def _level_of(paragraph: Paragraph) -> int:
    name = (paragraph.style.name if paragraph.style is not None else "") or ""
    digits = "".join(c for c in name if c.isdigit())
    return min(max(int(digits), 1), 6) if name.startswith("Heading") and digits else 1


def starter_docx(title: str, description: str | None, fields: Iterable[tuple[str, str]]) -> bytes:
    """A first version of the template's document: a title and a table of label + placeholder.

    `fields` are (key, label) pairs. The person downloads it, makes it look the way they want
    in Word (keeping the placeholders) and uploads it back.
    """
    document = new_docx()
    document.add_heading(title, level=1)
    if description:
        document.add_paragraph(description)
    table = document.add_table(rows=1, cols=2)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Field"
    table.rows[0].cells[1].text = "Value"
    for cell in table.rows[0].cells:
        for run in cell.paragraphs[0].runs:
            run.bold = True
    for key, label in fields:
        row = table.add_row().cells
        row[0].text = label
        row[1].text = "{{" + key + "}}"
    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


__all__ = ["DocxFillError", "preview_docx", "starter_docx"]
