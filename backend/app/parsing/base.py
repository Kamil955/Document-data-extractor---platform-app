from dataclasses import dataclass


class ParseError(Exception):
    """The file could not be read as a document (corrupt, encrypted, wrong format)."""


@dataclass(frozen=True)
class Block:
    """One line or paragraph of text, with the place it came from.

    Parsers turn different file formats into the same list of blocks, so everything
    after parsing (chunking, embedding) does not care whether the source was PDF or DOCX.
    """

    text: str
    # 1-based page number. None for formats without fixed pages (DOCX).
    page: int | None
    is_heading: bool = False
