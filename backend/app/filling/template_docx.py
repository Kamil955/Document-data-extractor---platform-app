"""Working with the Word document of a template: a preview for the screen and a starter file."""

import io
import re
from collections.abc import Iterable, Iterator

from docx import Document as new_docx
from docx.document import Document as DocxDocument
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
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
    TemplateContent,
    TemplatePreview,
)

# A preview is for looking, not for reading a 300-page document: cut it short.
MAX_BLOCKS = 400
# The editor needs the whole document (saving rebuilds it), so its limit is higher and a
# longer document is refused instead of being cut: a cut document saved back would lose text.
MAX_EDIT_BLOCKS = 1500

# XML does not allow most control characters, and python-docx refuses them.
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def preview_docx(data: bytes, field_keys: Iterable[str]) -> TemplatePreview:
    """The structure and text of a DOCX as plain data, with its {{placeholders}} marked.

    The browser draws this itself (headings, bold, tables, placeholder chips). It is not
    converted to HTML on the server on purpose: text from a user's file never becomes markup,
    so there is nothing to sanitize and no way to smuggle a script into the page.
    """
    document = _open(data)
    keys = list(field_keys)  # the order of the template's fields, for the unused ones
    known = set(keys)

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
        unused_fields=[key for key in keys if key not in used],
        truncated=truncated,
    )


def read_content(data: bytes) -> TemplateContent:
    """Every block of the document, for the editor; refuses a document that is too long."""
    document = _open(data)
    blocks = []
    for block in _iter_blocks(document):
        if len(blocks) >= MAX_EDIT_BLOCKS:
            raise DocxFillError("the document is too long to edit here")
        blocks.append(_table_block(block) if isinstance(block, Table) else _paragraph_block(block))
    return TemplateContent(blocks=blocks, notes=_lossy_parts(document))


def _lossy_parts(document: DocxDocument) -> list[str]:
    """What saving from the editor would not keep, found by looking at the XML of the body."""
    body = document.element.body
    notes = []
    if body.xpath(".//w:drawing | .//w:pict"):
        notes.append("Images and drawings in the body are removed when you save.")
    if body.xpath(".//w:tc//w:tbl"):
        notes.append("Tables inside table cells are flattened into plain paragraphs.")
    if body.xpath(".//w:gridSpan | .//w:vMerge"):
        notes.append("Merged table cells become separate cells.")
    if body.xpath(".//w:hyperlink"):
        notes.append("Hyperlinks become plain text.")
    return notes


def build_docx(blocks: Iterable[PreviewParagraph | PreviewTable], base: bytes | None) -> bytes:
    """Write the blocks as the body of a DOCX.

    `base` is the template's current file. Its styles, headers, footers and page setup are
    kept: only the body is replaced, so a heading still looks like the company's heading.
    What is not kept: direct formatting inside a paragraph (fonts, colours, alignment) and
    images, which the editor does not model. With no base a new, empty document is used.
    """
    document = _open(base) if base is not None else new_docx()
    body = document.element.body
    for child in list(body):
        if child.tag != qn("w:sectPr"):  # the section properties hold the page setup
            body.remove(child)

    previous_was_table = False
    for block in blocks:
        if isinstance(block, PreviewTable):
            if previous_was_table:
                document.add_paragraph()  # two tables in a row would merge into one in Word
            _add_table(document, block)
            previous_was_table = True
        else:
            _fill_paragraph(document, document.add_paragraph(), block)
            previous_was_table = False

    output = io.BytesIO()
    document.save(output)
    return output.getvalue()


def _style(document: DocxDocument, name: str):
    try:
        return document.styles[name]
    except KeyError:
        return None  # an uploaded file does not have to define every built-in style


def _fill_paragraph(document: DocxDocument, paragraph: Paragraph, block: PreviewParagraph) -> None:
    style_name = {
        "title": "Title",
        "heading": f"Heading {min(max(block.level, 1), 9)}",
        "list": "List Bullet",
    }.get(block.style)
    style = _style(document, style_name) if style_name else None
    if style is not None:
        paragraph.style = style
    elif block.style == "list":
        # No bullet style in this file: a typed bullet and an indent still read as a list.
        paragraph.paragraph_format.left_indent = Pt(18)
        paragraph.add_run("\u2022 ")
    for segment in block.segments:
        run = paragraph.add_run(_CONTROL.sub("", segment.text))
        # No heading style in this file: bold text at least marks it as a heading.
        bold = segment.bold or (style is None and block.style in ("title", "heading"))
        run.bold = bold or None
        run.italic = segment.italic or None
        run.underline = segment.underline or None


def _add_table(document: DocxDocument, block: PreviewTable) -> None:
    columns = max((len(row) for row in block.rows), default=0)
    if columns == 0:
        return
    table = document.add_table(rows=len(block.rows), cols=columns)
    if _style(document, "Table Grid") is not None:
        table.style = "Table Grid"
    else:
        _set_borders(table)
    for row, cells in zip(table.rows, block.rows, strict=True):
        for cell, paragraphs in zip(row.cells, cells, strict=False):
            for index, paragraph_block in enumerate(paragraphs):
                paragraph = cell.paragraphs[0] if index == 0 else cell.add_paragraph()
                _fill_paragraph(document, paragraph, paragraph_block)


def _set_borders(table: Table) -> None:
    """Thin borders for a file without "Table Grid" (a table without borders is invisible)."""
    properties = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:color"), "808080")
        borders.append(element)
    properties.append(borders)


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


__all__ = ["DocxFillError", "build_docx", "preview_docx", "read_content", "starter_docx"]
