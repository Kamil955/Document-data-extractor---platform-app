import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.base import Embedder
from app.models import Chunk, Document


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    filename: str
    score: float  # cosine similarity: 1.0 = same direction, 0.0 = unrelated


async def search_chunks(
    session: AsyncSession,
    embedder: Embedder,
    query: str,
    *,
    limit: int = 5,
    document_id: uuid.UUID | None = None,
) -> list[SearchHit]:
    """Return the chunks whose meaning is closest to the query, best first."""
    query_vector = await embedder.embed_query(query)
    # <=> in SQL. pgvector returns a DISTANCE (0 = identical), the HNSW index is built
    # for exactly this operator (vector_cosine_ops), so ORDER BY + LIMIT can use it.
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
    statement = (
        select(Chunk, Document.filename, distance)
        .join(Document, Document.id == Chunk.document_id)
        # Vectors from different models live in different spaces: comparing them is
        # meaningless, so only chunks embedded by the current model are searched.
        .where(Chunk.embedding_model == embedder.model_name)
        .order_by(distance)
        .limit(limit)
    )
    if document_id is not None:
        statement = statement.where(Chunk.document_id == document_id)
    rows = (await session.execute(statement)).all()
    return [SearchHit(chunk, filename, 1.0 - dist) for chunk, filename, dist in rows]
