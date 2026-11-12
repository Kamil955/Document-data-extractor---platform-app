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
    created_at: datetime
