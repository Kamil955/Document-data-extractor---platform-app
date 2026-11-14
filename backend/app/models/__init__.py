# Importing every model here guarantees they are registered on Base.metadata
# before Alembic inspects it.
from app.models.base import Base
from app.models.chunk import EMBEDDING_DIM, Chunk
from app.models.document import Document, DocumentStatus
from app.models.template import FieldType, Template, TemplateField

__all__ = [
    "EMBEDDING_DIM",
    "Base",
    "Chunk",
    "Document",
    "DocumentStatus",
    "FieldType",
    "Template",
    "TemplateField",
]
