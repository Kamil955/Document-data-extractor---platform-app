import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DocumentStatus(enum.StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class Document(Base):
    """A source document (for example a contract) uploaded by the user."""

    __tablename__ = "documents"

    # UUID generated in Python: the id is known before the INSERT, so we can build
    # the storage key from it, and ids in URLs are not guessable like 1, 2, 3.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    # Key of the file in object storage; the file itself never goes into the database.
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    status: Mapped[DocumentStatus] = mapped_column(
        # native_enum=False stores a plain VARCHAR instead of a Postgres ENUM type:
        # adding a new status later is then a code change, not an ALTER TYPE migration.
        # values_callable stores "uploaded" (the value), not "UPLOADED" (the member name).
        Enum(
            DocumentStatus,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=DocumentStatus.UPLOADED,
    )
    # Why processing failed, shown to the user. NULL unless status is "failed".
    error: Mapped[str | None] = mapped_column(Text)
    # Set when a worker claims the document. If a worker dies mid-way the document stays
    # in "processing" forever, so another worker treats an old timestamp as abandoned work.
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
