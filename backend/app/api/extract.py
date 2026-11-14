import uuid

from fastapi import APIRouter, HTTPException

from app.api.deps import EmbedderDep, LLMDep, SessionDep
from app.embeddings.base import EmbedderUnavailableError, EmbeddingError
from app.llm.base import LLMUnavailableError
from app.models import Document, DocumentStatus, FieldType, Template
from app.retrieval.extract import FieldSpec, extract_fields
from app.schemas import CitationOut, ExtractRequest, ExtractResponse, FieldResultOut

router = APIRouter(tags=["extract"])


@router.post("/documents/{document_id}/extract", response_model=ExtractResponse)
async def extract(
    document_id: uuid.UUID,
    body: ExtractRequest,
    session: SessionDep,
    embedder: EmbedderDep,
    llm: LLMDep,
) -> ExtractResponse:
    """Fill in the fields of a template (or of an inline list) from one document.

    Every value comes with verified quotes from the document. The call is synchronous and
    takes a few seconds per field; storing results and running in the background comes with
    the verification screen.
    """
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    if document.status is not DocumentStatus.INDEXED:
        raise HTTPException(
            status_code=409, detail=f"document is not ready (status: {document.status.value})"
        )

    if body.template_id is not None:
        template = await session.get(Template, body.template_id)
        if template is None:
            raise HTTPException(status_code=404, detail="template not found")
        specs = [FieldSpec(f.key, f.label, f.description, f.field_type) for f in template.fields]
    else:
        assert body.fields is not None  # guaranteed by the request validator
        specs = [FieldSpec(f.key, f.label, f.description, FieldType(f.type)) for f in body.fields]

    try:
        results = await extract_fields(
            session, embedder, llm, specs, document_id=document_id, limit=body.limit
        )
    except (EmbedderUnavailableError, LLMUnavailableError) as exc:
        raise HTTPException(503, f"model service unavailable: {exc}") from exc
    except EmbeddingError as exc:
        raise HTTPException(400, f"field rejected by the embedding model: {exc}") from exc

    return ExtractResponse(
        document_id=document_id,
        template_id=body.template_id,
        model=llm.model_name,
        results=[
            FieldResultOut(
                key=r.key,
                label=r.label,
                type=r.field_type,
                value=r.value,
                found=r.found,
                supported=r.supported,
                citations=[CitationOut(**vars(c)) for c in r.citations],
                error=r.error,
            )
            for r in results
        ],
    )
