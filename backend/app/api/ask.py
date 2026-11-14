from fastapi import APIRouter, HTTPException

from app.api.deps import EmbedderDep, LLMDep, SessionDep
from app.embeddings.base import EmbedderUnavailableError, EmbeddingError
from app.llm.base import LLMError, LLMUnavailableError
from app.retrieval.ask import answer_question
from app.schemas import AskRequest, AskResponse, CitationOut, RetrievedOut

router = APIRouter(tags=["ask"])


@router.post("/ask", response_model=AskResponse)
async def ask(body: AskRequest, session: SessionDep, embedder: EmbedderDep, llm: LLMDep):
    try:
        result = await answer_question(
            session,
            embedder,
            llm,
            body.question,
            limit=body.limit,
            document_id=body.document_id,
        )
    except (EmbedderUnavailableError, LLMUnavailableError) as exc:
        # 503: temporary, on our side (Ollama down or model missing); the client may retry.
        raise HTTPException(503, f"model service unavailable: {exc}") from exc
    except EmbeddingError as exc:
        raise HTTPException(400, f"question rejected by the embedding model: {exc}") from exc
    except LLMError as exc:
        # 502: an upstream component answered with something we cannot use.
        raise HTTPException(502, f"the language model gave an unusable answer: {exc}") from exc
    return AskResponse(
        question=result.question,
        found=result.found,
        answer=result.answer,
        supported=result.supported,
        citations=[CitationOut(**vars(c)) for c in result.citations],
        retrieved=[
            RetrievedOut(
                chunk_id=hit.chunk.id,
                page_start=hit.chunk.page_start,
                section_path=hit.chunk.section_path,
                score=hit.score,
            )
            for hit in result.retrieved
        ],
        model=result.model,
    )
