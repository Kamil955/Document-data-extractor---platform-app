import io
import logging
import uuid
import zipfile
from collections.abc import Sequence
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response, UploadFile
from sqlalchemy import select

from app.api.deps import SessionDep, SettingsDep, StorageDep
from app.core.content_types import DOCX_MIME, PDF_MIME
from app.models import Chunk, Document, DocumentStatus
from app.schemas import ChunkOut, DocumentOut
from app.storage.base import BlobNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["documents"])


def detect_content_type(data: bytes) -> str | None:
    """Decide the file type from its bytes, not from what the client claims.

    The Content-Type header and the file extension are chosen by the sender, so they
    prove nothing. The first bytes of the file do.
    """
    if data.startswith(b"%PDF-"):
        return PDF_MIME
    if data.startswith(b"PK\x03\x04"):
        # A DOCX is a ZIP archive, but so are thousands of other formats. A real Word
        # document always contains word/document.xml.
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "word/document.xml" in archive.namelist():
                    return DOCX_MIME
        except zipfile.BadZipFile:
            return None
    return None


def clean_filename(raw: str | None) -> str:
    """Keep only the file name: browsers and scripts may send a whole path."""
    name = (raw or "document").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return (name or "document")[:255]  # the column is String(255)


@router.post("", status_code=201, response_model=DocumentOut)
async def upload_document(
    file: UploadFile,
    session: SessionDep,
    storage: StorageDep,
    settings: SettingsDep,
) -> Document:
    if file.size is not None and file.size > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="file too large")
    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="file too large")

    content_type = detect_content_type(data)
    if content_type is None:
        raise HTTPException(status_code=415, detail="only PDF and DOCX files are supported")

    # The id is generated here, before the INSERT, because the storage key is built from it.
    # The key is the UUID alone: the original filename never reaches the storage path,
    # so there is nothing to sanitize and no path-traversal risk.
    document_id = uuid.uuid4()
    storage_key = f"documents/{document_id}"
    document = Document(
        id=document_id,
        filename=clean_filename(file.filename),
        content_type=content_type,
        storage_key=storage_key,
    )

    # Order matters. The file goes first, the database row second:
    #  - blob saved, DB fails -> we delete the blob below (and an orphan blob is harmless);
    #  - the reverse order could leave a row pointing to a file that does not exist.
    await storage.put(storage_key, data, content_type)
    session.add(document)
    try:
        await session.commit()
    except Exception:
        await storage.delete(storage_key)  # compensation: undo the first step
        raise
    return document


@router.get("", response_model=list[DocumentOut])
async def list_documents(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Sequence[Document]:
    result = await session.execute(
        select(Document).order_by(Document.created_at.desc()).limit(limit).offset(offset)
    )
    return result.scalars().all()


@router.get("/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, session: SessionDep) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return document


@router.get("/{document_id}/file")
async def download_document(
    document_id: uuid.UUID, session: SessionDep, storage: StorageDep
) -> Response:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    try:
        data = await storage.get(document.storage_key)
    except BlobNotFoundError:
        logger.error("Blob missing for document %s (key %s)", document.id, document.storage_key)
        raise HTTPException(status_code=404, detail="file is missing from storage") from None
    # filename*=UTF-8''... is the RFC 5987 form: it carries non-ASCII names
    # (e.g. Polish letters) that a plain filename="..." cannot.
    disposition = f"attachment; filename*=UTF-8''{quote(document.filename)}"
    return Response(
        content=data,
        media_type=document.content_type,
        headers={"Content-Disposition": disposition},
    )


@router.get("/{document_id}/chunks", response_model=list[ChunkOut])
async def list_chunks(
    document_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Sequence[Chunk]:
    if await session.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="document not found")
    result = await session.execute(
        select(Chunk)
        .where(Chunk.document_id == document_id)
        .order_by(Chunk.chunk_index)
        .limit(limit)
        .offset(offset)
    )
    return result.scalars().all()


@router.post("/{document_id}/reprocess", response_model=DocumentOut)
async def reprocess_document(document_id: uuid.UUID, session: SessionDep) -> Document:
    """Queue a document for processing again (after a failure, or after changing the model).

    The API does not process anything itself: it only puts the document back in the queue.
    The worker picks it up, and replaces the old chunks atomically.
    """
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    if document.status is DocumentStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="document is being processed right now")
    document.status = DocumentStatus.UPLOADED
    document.error = None
    await session.commit()
    return document
