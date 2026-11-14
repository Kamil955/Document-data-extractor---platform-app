import copy
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Literal

from docx import Document as open_docx
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run

# {{key}} or {{ key }}. The key has the same shape as a template field key.
PLACEHOLDER = re.compile(r"\{\{\s*([a-z][a-z0-9_]{0,63})\s*\}\}")

Status = Literal["filled", "unverified", "missing"]

# What the reader of the filled document sees. Only the two cases that need attention are
# highlighted, so a clean document looks clean.
_HIGHLIGHT = {"unverified": WD_COLOR_INDEX.TURQUOISE, "missing": WD_COLOR_INDEX.YELLOW}


class DocxFillError(Exception):
    """The file could not be read as a DOCX."""


@dataclass(frozen=True)
class FillValue:
    label: str
    value: str
    status: Status


@dataclass
class FillReport:
    filled: list[str] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    # Placeholders in the file that no field of the extraction fills: left as they are.
    unknown: list[str] = field(default_factory=list)


def find_placeholders(data: bytes) -> list[str]:
    """Placeholder keys used in a DOCX, in order of first appearance."""
    document = _open(data)
    keys: dict[str, None] = {}
    for paragraph in _all_paragraphs(document):
        for match in PLACEHOLDER.finditer("".join(r.text for r in paragraph.runs)):
            keys.setdefault(match[1])
    return list(keys)


def fill_docx(data: bytes, values: dict[str, FillValue]) -> tuple[bytes, FillReport]:
    """Replace {{key}} placeholders with extracted values and return the new DOCX.

    Word often splits one visible placeholder into several runs ("{{gov" + "erning_law}}"),
    for example after spell-checking or when part of it was formatted. So matching is done on
    the text of the whole paragraph, and the replacement is mapped back onto the runs.
    The value takes the formatting of the run in which the placeholder began.

    Covered: body, tables (also nested), headers and footers. Not covered: text boxes,
    footnotes, content controls and runs inside hyperlinks.
    """
    document = _open(data)
    report = FillReport()
    seen: set[str] = set()
    for paragraph in _all_paragraphs(document):
        for key in _fill_paragraph(paragraph, values):
            if key in seen:
                continue
            seen.add(key)
            if key not in values:
                report.unknown.append(key)
            else:
                # The status AFTER display rules: a "filled" field with an empty value is missing.
                getattr(report, _display(values[key])[1]).append(key)
    output = io.BytesIO()
    document.save(output)
    return output.getvalue(), report


def _open(data: bytes):
    try:
        return open_docx(io.BytesIO(data))
    except Exception as exc:  # python-docx raises BadZipFile, KeyError, XML errors...
        raise DocxFillError(f"cannot read DOCX: {exc}") from exc


def _all_paragraphs(document) -> Iterator[Paragraph]:
    yield from _paragraphs_of(document)
    for section in document.sections:
        for part in (
            section.header,
            section.first_page_header,
            section.even_page_header,
            section.footer,
            section.first_page_footer,
            section.even_page_footer,
        ):
            yield from _paragraphs_of(part)


def _paragraphs_of(container) -> Iterator[Paragraph]:
    """Paragraphs of a body, header or cell, including tables nested in it."""
    yield from container.paragraphs
    for table in container.tables:
        yield from _paragraphs_of_table(table)


def _paragraphs_of_table(table: Table) -> Iterator[Paragraph]:
    for row in table.rows:
        for cell in row.cells:
            yield from _paragraphs_of(cell)


def _display(value: FillValue | None) -> tuple[str, Status | None]:
    if value is None:
        return "", None
    if value.status == "missing" or not value.value.strip():
        return f"[not found: {value.label}]", "missing"
    return value.value.strip(), value.status


def _fill_paragraph(paragraph: Paragraph, values: dict[str, FillValue]) -> list[str]:
    runs = paragraph.runs
    texts = [run.text for run in runs]
    full = "".join(texts)
    matches = [m for m in PLACEHOLDER.finditer(full) if m[1] in values]
    keys = [m[1] for m in PLACEHOLDER.finditer(full)]
    if not matches:
        return keys

    starts = [sum(len(t) for t in texts[:i]) for i in range(len(texts))]

    def run_at(offset: int) -> int:
        """Index of the run holding the character at `offset`."""
        return max(i for i, start in enumerate(starts) if start <= offset)

    # Last match first: replacing it does not move the offsets of the matches before it.
    for match in reversed(matches):
        start, end = match.span()
        first, last = run_at(start), run_at(end - 1)
        before = texts[first][: start - starts[first]]
        after = texts[last][end - starts[last] :]
        text, status = _display(values[match[1]])

        new_elements = [_value_run(runs[first], paragraph, text, status)]
        runs[first].text = before
        texts[first] = before
        for middle in range(first + 1, last):
            runs[middle].text = ""
            texts[middle] = ""
        if last == first:
            if after:
                new_elements.append(_copy_run(runs[first], paragraph, after))
        else:
            runs[last].text = after
            texts[last] = after
        anchor = runs[first]._r
        for element in new_elements:
            anchor.addnext(element)
            anchor = element
    return keys


def _copy_run(source: Run, paragraph: Paragraph, text: str):
    """A new run element with the formatting of `source` and the given text."""
    element = copy.deepcopy(source._r)
    for child in list(element):
        if child.tag != qn("w:rPr"):
            element.remove(child)
    Run(element, paragraph).text = text
    return element


def _value_run(source: Run, paragraph: Paragraph, text: str, status: Status | None):
    element = _copy_run(source, paragraph, text)
    if status in _HIGHLIGHT:
        Run(element, paragraph).font.highlight_color = _HIGHLIGHT[status]
    return element
