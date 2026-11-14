import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# The vector width is part of the database schema, so it lives next to the model.
# Changing the embedding model to one with another width means a new migration
# and re-embedding every chunk. Qwen3-Embedding-0.6B and BGE-M3 both produce 1024.
EMBEDDING_DIM = 1024


class Chunk(Base):
    """A fragment of a document, with the vector used to find it by meaning."""

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    # ON DELETE CASCADE at the database level: deleting a document removes its chunks
    # in the same statement, with no application code that could forget to do it.
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    # Position inside the document. Together with document_id it is unique, which makes
    # "chunk 3 of document X" a stable address (useful for citations).
    chunk_index: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    # Pages are NULL for DOCX: a Word file has no fixed pages (they depend on the renderer).
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section_path: Mapped[str | None] = mapped_column(String(500))
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    # Which model produced the vector. Vectors from different models are not comparable,
    # so after a model change this column tells us exactly which rows must be recomputed.
    embedding_model: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index"),
        # HNSW = approximate nearest-neighbour index. vector_cosine_ops makes it serve
        # queries that order by cosine distance (the <=> operator).
        Index(
            "ix_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        # GIN index for keyword search (see app.retrieval.search). The expression must be
        # identical to the one used in queries, otherwise Postgres will not use the index.
        Index(
            "ix_chunks_text_fts",
            sql_text("to_tsvector('english'::regconfig, text)"),
            postgresql_using="gin",
        ),
    )
