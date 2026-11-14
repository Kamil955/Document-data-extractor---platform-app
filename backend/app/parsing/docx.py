import io

from docx import Document as open_docx
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.parsing.base import Block, ParseError
from app.parsing.headings import expand_run_in_headings, looks_like_heading


def parse_docx(data: bytes) -> list[Block]:
    try:
        document = open_docx(io.BytesIO(data))
    except Exception as exc:
        # Same reasoning as for PDF: python-docx raises BadZipFile, KeyError, XML errors...
        raise ParseError(f"cannot read DOCX: {exc}") from exc

    blocks: list[Block] = []
    # Walk the body in document order. document.paragraphs and document.tables are two
    # separate lists, so using them would lose the position of a table between paragraphs.
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if text:
                # A Word document says explicitly what a heading is: its paragraph style.
                style = (paragraph.style.name if paragraph.style is not None else "") or ""
                # Word marks table-of-contents entries with the styles "TOC 1", "TOC 2"...
                if style.lower().startswith("toc "):
                    continue
                is_heading = style.startswith(("Heading", "Title")) or looks_like_heading(text)
                blocks.append(Block(text, None, is_heading))
        elif child.tag.endswith("}tbl"):
            # One block per row, cells separated by " | ", so a row stays readable as text.
            for row in Table(child, document).rows:
                cells = [cell.text.strip() for cell in row.cells]
                line = " | ".join(cell for cell in cells if cell)
                if line:
                    blocks.append(Block(line, None, False))
    return expand_run_in_headings(blocks)
