import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ExtractionStatus(enum.StrEnum):
    PENDING = "pending"  # waiting for the worker
    RUNNING = "running"  # the worker is going through the fields
    COMPLETED = "completed"
    FAILED = "failed"


class Extraction(Base):
    """The saved result of extracting a template's fields from one document.

    Extraction takes tens of seconds, so the API only records the request (status "pending")
    and the worker fills `results` field by field. Filling a Word file, showing the result for
    verification or downloading it again then costs nothing.
    """

    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    # SET NULL: deleting a template must not destroy results that were already produced.
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL")
    )
    model: Mapped[str] = mapped_column(String(100))
    status: Mapped[ExtractionStatus] = mapped_column(
        # Plain VARCHAR like Document.status: a new status is a code change, not ALTER TYPE.
        Enum(
            ExtractionStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ExtractionStatus.PENDING,
        index=True,
    )
    # The fields to extract (key, label, description, type), copied from the template when the
    # request is made. A snapshot, not a reference: the template may be edited or deleted while
    # the worker is still busy, and an inline field list has no template at all.
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    # How many chunks the model sees per field (see ExtractRequest.limit).
    retrieval_limit: Mapped[int] = mapped_column(Integer)
    # One entry per FINISHED field (value, found, supported, citations, ...), in the order of
    # `fields`. The worker appends as it goes, so progress is len(results) / len(fields).
    # JSONB, not a table: the shape of a field result may still change.
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    # Why the extraction failed. NULL unless status is "failed".
    error: Mapped[str | None] = mapped_column(Text)
    # Set when the worker claims the extraction and refreshed after every field. An old value
    # on a "running" extraction means the worker died, so another one may take it over.
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
