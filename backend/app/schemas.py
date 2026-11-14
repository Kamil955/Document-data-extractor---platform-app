import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import DocumentStatus, FieldType


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
    # "vector" = meaning only (default; best in our measurements); "hybrid" = + keywords.
    mode: Literal["hybrid", "vector"] = "vector"


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


# Keys are used as placeholders in DOCX templates ("{{notice_period}}"), so they are restricted
# to a form that is safe there and easy to type.
_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class FieldIn(BaseModel):
    key: str = Field(description="Machine name: lowercase letters, digits and underscores.")
    label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    type: FieldType = FieldType.TEXT

    @field_validator("key")
    @classmethod
    def key_is_a_slug(cls, value: str) -> str:
        if not _KEY.match(value):
            raise ValueError("key must match [a-z][a-z0-9_]{0,63}")
        return value


def _reject_duplicate_keys(fields: list[FieldIn]) -> list[FieldIn]:
    keys = [f.key for f in fields]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise ValueError(f"duplicate field keys: {', '.join(duplicates)}")
    return fields


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    fields: list[FieldIn] = Field(min_length=1, max_length=100)

    @field_validator("fields")
    @classmethod
    def keys_are_unique(cls, value: list[FieldIn]) -> list[FieldIn]:
        return _reject_duplicate_keys(value)


class FieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    description: str | None
    # The database column is field_type; the API calls it "type" like the request does.
    type: FieldType = Field(validation_alias="field_type")


class TemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    fields: list[FieldOut]


class ExtractRequest(BaseModel):
    """Extract fields from one document: either a stored template or an inline field list."""

    template_id: uuid.UUID | None = None
    fields: list[FieldIn] | None = Field(default=None, min_length=1, max_length=100)
    # More chunks than /ask uses: a short field query lands less precisely than a full
    # question, and measured on real contracts 10 chunks found values that 5 missed.
    limit: int = Field(default=8, ge=1, le=10)

    @field_validator("fields")
    @classmethod
    def keys_are_unique(cls, value: list[FieldIn] | None) -> list[FieldIn] | None:
        return None if value is None else _reject_duplicate_keys(value)

    @model_validator(mode="after")
    def exactly_one_source(self) -> "ExtractRequest":
        if (self.template_id is None) == (self.fields is None):
            raise ValueError("give either template_id or fields, not both and not neither")
        return self


class FieldResultOut(BaseModel):
    key: str
    label: str
    type: FieldType
    value: str
    found: bool
    # found AND a verified citation. found=True with supported=False needs a human check.
    supported: bool
    citations: list[CitationOut]
    # The chunks the model was given for this field: what to look at when a value is missing.
    retrieved: list[RetrievedOut]
    error: str | None
    # True when a person typed or corrected the value: it counts as verified by that person.
    # Default False so results stored before this field existed still load.
    edited: bool = False


class ExtractResponse(BaseModel):
    # Id of the saved extraction: use it to read the result again or to fill a Word file.
    extraction_id: uuid.UUID
    document_id: uuid.UUID
    template_id: uuid.UUID | None
    model: str
    results: list[FieldResultOut]


class ValueUpdate(BaseModel):
    """A person's correction of one extracted value. An empty value means "not stated"."""

    value: str = Field(max_length=5000)
