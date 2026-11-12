from app.core.content_types import DOCX_MIME, PDF_MIME
from app.parsing.base import Block, ParseError
from app.parsing.docx import parse_docx
from app.parsing.pdf import parse_pdf

__all__ = ["Block", "ParseError", "parse_document"]


def parse_document(data: bytes, content_type: str) -> list[Block]:
    if content_type == PDF_MIME:
        return parse_pdf(data)
    if content_type == DOCX_MIME:
        return parse_docx(data)
    raise ParseError(f"unsupported content type: {content_type}")
