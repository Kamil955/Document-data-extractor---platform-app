import asyncio
import uuid
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Response, UploadFile

from app.api.deps import SessionDep, SettingsDep
from app.api.documents import clean_filename, detect_content_type
from app.core.content_types import DOCX_MIME
from app.filling.docx import DocxFillError, FillValue, fill_docx
from app.models import Extraction
from app.schemas import ExtractResponse, FieldResultOut

router = APIRouter(prefix="/extractions", tags=["extractions"])


def _response(extraction: Extraction) -> ExtractResponse:
    return ExtractResponse(
        extraction_id=extraction.id,
        document_id=extraction.document_id,
        template_id=extraction.template_id,
        model=extraction.model,
        results=[FieldResultOut(**item) for item in extraction.results],
    )


@router.get("/{extraction_id}", response_model=ExtractResponse)
async def get_extraction(extraction_id: uuid.UUID, session: SessionDep) -> ExtractResponse:
    extraction = await session.get(Extraction, extraction_id)
    if extraction is None:
        raise HTTPException(status_code=404, detail="extraction not found")
    return _response(extraction)


@router.post("/{extraction_id}/fill")
async def fill_template(
    extraction_id: uuid.UUID, file: UploadFile, session: SessionDep, settings: SettingsDep
) -> Response:
    """Fill a Word file with the values of a saved extraction.

    The file holds placeholders such as {{governing_law}} (the field keys). The response is
    the filled DOCX; the counts are in the X-Fill-* headers. Values that were not found are
    marked in yellow in the document, values without a verified quote in turquoise.
    """
    extraction = await session.get(Extraction, extraction_id)
    if extraction is None:
        raise HTTPException(status_code=404, detail="extraction not found")
    if file.size is not None and file.size > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="file too large")
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="file too large")
    if detect_content_type(data) != DOCX_MIME:
        raise HTTPException(status_code=415, detail="the template must be a DOCX file")

    values: dict[str, FillValue] = {}
    for item in extraction.results:
        if item["found"] and item["supported"]:
            status = "filled"
        elif item["found"]:
            status = "unverified"  # a value, but no verified quote: a human should check it
        else:
            status = "missing"
        values[item["key"]] = FillValue(item["label"], item["value"], status)

    try:
        # python-docx is synchronous and CPU-bound: a thread keeps the event loop free.
        filled, report = await asyncio.to_thread(fill_docx, data, values)
    except DocxFillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    disposition = f"attachment; filename*=UTF-8''{quote('filled-' + clean_filename(file.filename))}"
    return Response(
        content=filled,
        media_type=DOCX_MIME,
        headers={
            "Content-Disposition": disposition,
            "X-Fill-Filled": str(len(report.filled)),
            "X-Fill-Unverified": ",".join(report.unverified),
            "X-Fill-Missing": ",".join(report.missing),
            "X-Fill-Unknown": ",".join(report.unknown),
        },
    )
