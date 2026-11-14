import re
import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import Select, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.base import Embedder
from app.models import Chunk, Document

SearchMode = Literal["hybrid", "vector"]

# The text-search configuration: it decides stemming ("paid" ~ "pays") and stop words. The
# platform targets English documents; another language needs another configuration here AND
# in the migration that creates the index (the query must use the same expression).
FTS_CONFIG = "english"
_FTS_CONFIG_SQL = literal_column(f"'{FTS_CONFIG}'::regconfig")

# Reciprocal Rank Fusion constant. 60 is the value from the original paper and works well
# without tuning: it keeps one list's rank-1 from drowning the other list completely.
_RRF_K = 60
# Candidates taken from EACH ranking before fusing. A chunk that is 12th by meaning but 1st
# by keywords must still be able to win, so the pool is larger than the final `limit`.
_MIN_POOL = 20


@dataclass(frozen=True)
class SearchHit:
    chunk: Chunk
    filename: str
    score: float  # cosine similarity: 1.0 = same direction, 0.0 = unrelated


def fts_vector():
    """to_tsvector over the chunk text. Must match the expression of the GIN index."""
    return func.to_tsvector(_FTS_CONFIG_SQL, Chunk.text)


def keyword_query(query: str) -> str | None:
    """Turn free text into an OR query for Postgres ("payment | terms | paid").

    Word characters only, so user text can never inject tsquery syntax. OR, not AND: a long
    field description rarely has all its words in one chunk, and ranking sorts out the rest.
    Stop words are dropped by the text-search configuration itself.
    """
    words = dict.fromkeys(w.lower() for w in re.findall(r"\w{3,}", query))
    return " | ".join(words) or None


def _base(embedder: Embedder, document_id: uuid.UUID | None, distance) -> Select:
    statement = (
        select(Chunk, Document.filename, distance)
        .join(Document, Document.id == Chunk.document_id)
        # Vectors from different models live in different spaces: comparing them is
        # meaningless, so only chunks embedded by the current model are searched.
        .where(Chunk.embedding_model == embedder.model_name)
    )
    if document_id is not None:
        statement = statement.where(Chunk.document_id == document_id)
    return statement


async def search_chunks(
    session: AsyncSession,
    embedder: Embedder,
    query: str,
    *,
    limit: int = 5,
    document_id: uuid.UUID | None = None,
    mode: SearchMode = "vector",
) -> list[SearchHit]:
    """Return the best chunks for a query.

    "vector" (default): by meaning only (embeddings). Finds paraphrases, but a short generic
    query can land on loosely related text.
    "hybrid": meaning AND keywords. Postgres full-text search finds exact terms
    ("governed", "paid") that embeddings blur; the two rankings are merged with Reciprocal
    Rank Fusion, which uses only ranks, so the incomparable scores need no calibration.

    Why vector is the default: measured on three real contracts, hybrid was WORSE (hit@1 100% ->
    79% on one, 80% -> 60% on another). Postgres ts_rank_cd ignores how common a word is, so
    generic words ("contractor", "provider") add noise, and RRF weighs both lists equally.
    Hybrid stays available for tuning (weights, rarer-terms-only) and for comparing in the
    evaluation; do not make it the default without measuring again.

    `score` is always the cosine similarity, also for chunks found only by keywords.
    """
    query_vector = await embedder.embed_query(query)
    # <=> in SQL. pgvector returns a DISTANCE (0 = identical), the HNSW index is built
    # for exactly this operator (vector_cosine_ops), so ORDER BY + LIMIT can use it.
    distance = Chunk.embedding.cosine_distance(query_vector).label("distance")
    pool = limit if mode == "vector" else max(limit * 4, _MIN_POOL)

    by_meaning = (
        await session.execute(_base(embedder, document_id, distance).order_by(distance).limit(pool))
    ).all()

    ts_query_text = keyword_query(query) if mode == "hybrid" else None
    by_keywords: list = []
    if ts_query_text is not None:
        ts_query = func.to_tsquery(_FTS_CONFIG_SQL, ts_query_text)
        by_keywords = (
            await session.execute(
                _base(embedder, document_id, distance)
                .where(fts_vector().op("@@")(ts_query))
                .order_by(func.ts_rank_cd(fts_vector(), ts_query, 1).desc())
                .limit(pool)
            )
        ).all()

    fused: dict[uuid.UUID, float] = {}
    rows: dict[uuid.UUID, tuple[Chunk, str, float]] = {}
    for ranking in (by_meaning, by_keywords):
        for rank, (chunk, filename, dist) in enumerate(ranking, start=1):
            fused[chunk.id] = fused.get(chunk.id, 0.0) + 1.0 / (_RRF_K + rank)
            rows[chunk.id] = (chunk, filename, dist)
    best = sorted(fused, key=lambda chunk_id: fused[chunk_id], reverse=True)[:limit]
    return [SearchHit(rows[i][0], rows[i][1], 1.0 - rows[i][2]) for i in best]
