import asyncio
import logging
import uuid
from collections.abc import Sequence
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import LLMDep, SessionDep, SettingsDep, StorageDep
from app.api.documents import clean_filename, detect_content_type
from app.core.content_types import DOCX_MIME
from app.filling.docx import DocxFillError, find_placeholders
from app.filling.template_docx import build_docx, preview_docx, read_content, starter_docx
from app.llm.base import LLMError, LLMUnavailableError
from app.llm.rewrite import rewrite_passage
from app.models import FieldType, Template, TemplateField
from app.schemas import (
    ContentUpdate,
    RewriteRequest,
    RewriteResponse,
    TemplateContent,
    TemplateCreate,
    TemplateOut,
    TemplatePreview,
)
from app.storage.base import BlobNotFoundError, BlobStorage

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["templates"])


def _docx_key(template_id: uuid.UUID) -> str:
    # The key is the UUID alone (like for documents): the file name never reaches the storage path.
    return f"templates/{template_id}.docx"


async def _read_docx(file: UploadFile, max_bytes: int) -> bytes:
    if file.size is not None and file.size > max_bytes:
        raise HTTPException(status_code=413, detail="file too large")
    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="file too large")
    if detect_content_type(data) != DOCX_MIME:
        raise HTTPException(status_code=415, detail="the template document must be a DOCX file")
    return data


async def _placeholders(data: bytes) -> list[str]:
    try:
        # python-docx is synchronous and CPU-bound: a thread keeps the event loop free.
        return await asyncio.to_thread(find_placeholders, data)
    except DocxFillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _template(session: AsyncSession, template_id: uuid.UUID) -> Template:
    template = await session.get(Template, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="template not found")
    return template


async def _stored_docx(template: Template, storage: BlobStorage) -> bytes:
    if template.docx_key is None:
        raise HTTPException(status_code=404, detail="the template has no document yet")
    try:
        return await storage.get(template.docx_key)
    except BlobNotFoundError:
        logger.error("Blob missing for template %s (key %s)", template.id, template.docx_key)
        raise HTTPException(
            status_code=404, detail="the document is missing from storage"
        ) from None


async def _attach_docx(
    session: AsyncSession, storage: BlobStorage, template: Template, data: bytes, filename: str
) -> None:
    """Store a DOCX for a template. Same order as for documents: the file first, then the row."""
    key = _docx_key(template.id)
    # A template's document is replaced on purpose (upload, editor save): overwrite.
    await storage.put(key, data, DOCX_MIME, overwrite=True)
    template.docx_key = key
    template.docx_filename = clean_filename(filename)
    await session.commit()


@router.post("", status_code=201, response_model=TemplateOut)
async def create_template(body: TemplateCreate, session: SessionDep) -> Template:
    template = Template(
        name=body.name,
        description=body.description,
        # position keeps the order the client sent: the order of fields in a card matters.
        fields=[
            TemplateField(
                key=f.key,
                label=f.label,
                description=f.description,
                field_type=FieldType(f.type),
                position=position,
            )
            for position, f in enumerate(body.fields)
        ],
    )
    session.add(template)
    await session.commit()
    return template


def _label_from_key(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()


@router.post("/from-docx", status_code=201, response_model=TemplateOut)
async def create_template_from_docx(
    file: UploadFile,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
    name: Annotated[str | None, Form(max_length=200)] = None,
) -> Template:
    """Create a template from a Word file: every {{placeholder}} becomes a text field.

    The file is kept with the template, so it can be previewed and filled later without
    uploading it again. Labels are made from the keys ("governing_law" -> "Governing law");
    they, and the types, can be refined afterwards.
    """
    data = await _read_docx(file, settings.max_upload_bytes)
    keys = await _placeholders(data)
    if not keys:
        raise HTTPException(
            status_code=422,
            detail="no {{placeholders}} found in the document (example: {{governing_law}})",
        )

    filename = clean_filename(file.filename)
    default_name = filename.rsplit(".", 1)[0].replace("_", " ").strip() or "Template"
    template = Template(
        name=(name or "").strip() or default_name,
        fields=[
            TemplateField(
                key=key, label=_label_from_key(key), field_type=FieldType.TEXT, position=position
            )
            for position, key in enumerate(keys)
        ],
    )
    session.add(template)
    await session.flush()  # the id is needed for the storage key
    await storage.put(_docx_key(template.id), data, DOCX_MIME)
    template.docx_key = _docx_key(template.id)
    template.docx_filename = filename
    try:
        await session.commit()
    except Exception:
        await storage.delete(_docx_key(template.id))  # compensation, as for documents
        raise
    return template


@router.get("", response_model=list[TemplateOut])
async def list_templates(session: SessionDep) -> Sequence[Template]:
    result = await session.execute(select(Template).order_by(Template.created_at.desc()))
    return result.scalars().all()


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(template_id: uuid.UUID, session: SessionDep) -> Template:
    return await _template(session, template_id)


@router.put("/{template_id}/docx", response_model=TemplateOut)
async def put_template_docx(
    template_id: uuid.UUID,
    file: UploadFile,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> Template:
    """Attach a Word document to a template, or replace the one it has."""
    template = await _template(session, template_id)
    data = await _read_docx(file, settings.max_upload_bytes)
    await _placeholders(data)  # rejects a file that is not readable as a Word document
    await _attach_docx(session, storage, template, data, file.filename or "template.docx")
    return template


@router.post("/{template_id}/docx/generate", response_model=TemplateOut)
async def generate_template_docx(
    template_id: uuid.UUID, session: SessionDep, storage: StorageDep
) -> Template:
    """Make a first Word document from the fields (a table of label and placeholder).

    Download it, adjust it in Word (keep the placeholders) and upload it back. A template
    that already has a document is not overwritten: replace that one with PUT instead.
    """
    template = await _template(session, template_id)
    if template.docx_key is not None:
        raise HTTPException(status_code=409, detail="the template already has a document")
    data = await asyncio.to_thread(
        starter_docx,
        template.name,
        template.description,
        [(f.key, f.label) for f in template.fields],
    )
    await _attach_docx(session, storage, template, data, f"{template.name}.docx")
    return template


@router.get("/{template_id}/docx")
async def download_template_docx(
    template_id: uuid.UUID, session: SessionDep, storage: StorageDep
) -> Response:
    template = await _template(session, template_id)
    data = await _stored_docx(template, storage)
    disposition = f"attachment; filename*=UTF-8''{quote(template.docx_filename or 'template.docx')}"
    return Response(
        content=data, media_type=DOCX_MIME, headers={"Content-Disposition": disposition}
    )


@router.get("/{template_id}/preview", response_model=TemplatePreview)
async def preview_template(
    template_id: uuid.UUID, session: SessionDep, storage: StorageDep
) -> TemplatePreview:
    """The document of a template as data for the screen, placeholders marked."""
    template = await _template(session, template_id)
    data = await _stored_docx(template, storage)
    try:
        return await asyncio.to_thread(preview_docx, data, [f.key for f in template.fields])
    except DocxFillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{template_id}/content", response_model=TemplateContent)
async def get_template_content(
    template_id: uuid.UUID, session: SessionDep, storage: StorageDep
) -> TemplateContent:
    """The whole document for the editor. Unlike the preview, it is never cut short."""
    template = await _template(session, template_id)
    data = await _stored_docx(template, storage)
    try:
        return await asyncio.to_thread(read_content, data)
    except DocxFillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{template_id}/content", response_model=TemplateOut)
async def put_template_content(
    template_id: uuid.UUID, body: ContentUpdate, session: SessionDep, storage: StorageDep
) -> Template:
    """Save what the editor sends as the body of the template's document.

    The styles, headers and page setup of the current file are kept; a template without a
    document gets a new one.
    """
    template = await _template(session, template_id)
    base = await _stored_docx(template, storage) if template.docx_key else None
    try:
        data = await asyncio.to_thread(build_docx, body.blocks, base)
    except DocxFillError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _attach_docx(
        session, storage, template, data, template.docx_filename or f"{template.name}.docx"
    )
    return template


@router.post("/rewrite", response_model=RewriteResponse)
async def rewrite(body: RewriteRequest, llm: LLMDep) -> RewriteResponse:
    """Rewrite a passage following the person's instruction ("make it more formal")."""
    try:
        text = await rewrite_passage(llm, body.text, body.instruction, body.context)
    except LLMUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RewriteResponse(text=text)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID, session: SessionDep, storage: StorageDep
) -> Response:
    template = await _template(session, template_id)
    key = template.docx_key
    await session.delete(template)  # fields go with it (ON DELETE CASCADE)
    await session.commit()
    if key is not None:
        # After the commit, like for documents: a leftover file is harmless, a row without
        # its file would not be.
        await storage.delete(key)
    return Response(status_code=204)
