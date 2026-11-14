from fastapi import APIRouter, HTTPException

from app.api.deps import EmbedderDep, SessionDep
from app.embeddings.base import EmbedderUnavailableError, EmbeddingError
from app.retrieval.search import search_chunks
from app.schemas import SearchHitOut, SearchRequest

router = APIRouter(tags=["search"])


@router.post("/search", response_model=list[SearchHitOut])
async def search(body: SearchRequest, session: SessionDep, embedder: EmbedderDep):
    try:
        hits = await search_chunks(
            session,
            embedder,
            body.query,
            limit=body.limit,
            document_id=body.document_id,
            mode=body.mode,
        )
    except EmbedderUnavailableError as exc:
        # 503: the problem is temporary and on our side (Ollama down), the client may retry.
        raise HTTPException(503, f"embedding service unavailable: {exc}") from exc
    except EmbeddingError as exc:
        raise HTTPException(400, f"query rejected by the embedding model: {exc}") from exc
    return [
        SearchHitOut(
            chunk_id=hit.chunk.id,
            document_id=hit.chunk.document_id,
            filename=hit.filename,
            chunk_index=hit.chunk.chunk_index,
            text=hit.chunk.text,
            page_start=hit.chunk.page_start,
            page_end=hit.chunk.page_end,
            section_path=hit.chunk.section_path,
            score=hit.score,
        )
        for hit in hits
    ]
