import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import DocumentStatus


class DocumentOut(BaseModel):
    """Document metadata returned by the API (never the file itself, never storage_key)."""

    # from_attributes lets Pydantic read the fields straight from a SQLAlchemy object.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    status: DocumentStatus
    # Why processing failed (only set when status is "failed").
    error: str | None
    created_at: datetime


class ChunkOut(BaseModel):
    """A chunk without its vector: 1024 floats per row would only bloat the response."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None
    section_path: str | None
    embedding_model: str
