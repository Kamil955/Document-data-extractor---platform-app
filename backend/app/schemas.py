import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=20)
    # Restrict the search to one document; None searches all of them.
    document_id: uuid.UUID | None = None


class SearchHitOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    chunk_index: int
    text: str
    page_start: int | None
    page_end: int | None
    section_path: str | None
    score: float


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    # How many chunks are given to the model as context.
    limit: int = Field(default=5, ge=1, le=10)
    document_id: uuid.UUID | None = None


class CitationOut(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_start: int | None
    page_end: int | None
    section_path: str | None
    quote: str
    # False means the quote was NOT found in the cited chunk: do not trust it.
    verified: bool


class RetrievedOut(BaseModel):
    chunk_id: uuid.UUID
    page_start: int | None
    section_path: str | None
    score: float


class AskResponse(BaseModel):
    question: str
    found: bool
    answer: str
    # found AND at least one verified citation. found=True with supported=False is an answer
    # the model could not back with a real quote: show it with a warning, not as fact.
    supported: bool
    citations: list[CitationOut]
    retrieved: list[RetrievedOut]
    model: str
