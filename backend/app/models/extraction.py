import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Extraction(Base):
    """The saved result of extracting a template's fields from one document.

    Extraction takes tens of seconds, so it is done once and stored. Filling a Word file,
    showing the result for verification or downloading it again then costs nothing.
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
    # One entry per field (value, found, supported, citations, ...), exactly as the API returned
    # it. JSONB, not a table: the whole list is always read and written together, and the
    # shape of a field result may still change.
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
