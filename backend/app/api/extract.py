import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import LLMDep, SessionDep
from app.api.extractions import extraction_response
from app.models import Document, DocumentStatus, Extraction, ExtractionStatus, Template
from app.schemas import ExtractionSummary, ExtractRequest, ExtractResponse

router = APIRouter(tags=["extract"])


@router.post("/documents/{document_id}/extract", response_model=ExtractResponse, status_code=202)
async def extract(
    document_id: uuid.UUID, body: ExtractRequest, session: SessionDep, llm: LLMDep
) -> ExtractResponse:
    """Start extracting the fields of a template (or of an inline list) from one document.

    Extraction takes a few seconds per field, so this only records the request and answers
    at once with 202 Accepted. The worker fills in the fields one by one: poll
    GET /extractions/{extraction_id} until its status is "completed" (or "failed").
    Every value comes with verified quotes from the document.
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
        fields = [
            {
                "key": f.key,
                "label": f.label,
                "description": f.description,
                "type": f.field_type.value,
            }
            for f in template.fields
        ]
    else:
        assert body.fields is not None  # guaranteed by the request validator
        fields = [
            {"key": f.key, "label": f.label, "description": f.description, "type": f.type.value}
            for f in body.fields
        ]

    extraction = Extraction(
        document_id=document_id,
        template_id=body.template_id,
        # The worker overwrites this with the model it really uses when it picks the job up.
        model=llm.model_name,
        status=ExtractionStatus.PENDING,
        fields=fields,  # a snapshot, see the model
        retrieval_limit=body.limit,
        results=[],
    )
    session.add(extraction)
    await session.commit()
    return extraction_response(extraction)


@router.get("/documents/{document_id}/extractions", response_model=list[ExtractionSummary])
async def list_extractions(document_id: uuid.UUID, session: SessionDep) -> list[ExtractionSummary]:
    """The extractions made from one document, newest first."""
    if await session.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="document not found")
    rows = await session.execute(
        select(Extraction, Template.name)
        .outerjoin(Template, Extraction.template_id == Template.id)
        .where(Extraction.document_id == document_id)
        .order_by(Extraction.created_at.desc())
    )
    return [
        ExtractionSummary(
            extraction_id=extraction.id,
            template_id=extraction.template_id,
            template_name=template_name,
            model=extraction.model,
            status=extraction.status,
            total=len(extraction.fields),
            done=len(extraction.results),
            created_at=extraction.created_at,
        )
        for extraction, template_name in rows
    ]
