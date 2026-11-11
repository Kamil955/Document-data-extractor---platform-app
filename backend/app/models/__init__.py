# Importing every model here guarantees they are registered on Base.metadata
# before Alembic inspects it.
from app.models.base import Base
from app.models.document import Document, DocumentStatus

__all__ = ["Base", "Document", "DocumentStatus"]
