import asyncio
import enum
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal, engine
from app.embeddings.base import Embedder, EmbedderUnavailableError
from app.embeddings.ollama import OllamaEmbedder
from app.ingestion.chunking import chunk_blocks
from app.models import EMBEDDING_DIM, Chunk, Document, DocumentStatus
from app.parsing import parse_document
from app.storage.azure_blob import AzureBlobStorage
from app.storage.base import BlobStorage

logger = logging.getLogger(__name__)


class RunResult(enum.Enum):
    IDLE = "idle"  # nothing to do
    PROCESSED = "processed"  # one document finished (indexed or failed)
    DEFERRED = "deferred"  # embedding service down: document put back in the queue


@dataclass(frozen=True)
class ClaimedDocument:
    """The few fields the worker needs, copied out of the ORM object.

    After a commit or rollback an ORM object may be expired, and touching an expired
    attribute in async code raises an error. A plain dataclass has no such trap.
    """

    id: object
    storage_key: str
    content_type: str


async def claim_next_document(
    session: AsyncSession, stale_after: timedelta
) -> ClaimedDocument | None:
    """Take one document for processing, so no other worker takes the same one.

    FOR UPDATE SKIP LOCKED is the heart of a queue built on Postgres: the row is locked
    for this transaction, and a concurrent worker running the same query skips locked
    rows instead of waiting for them. Two workers therefore never pick the same document,
    and neither blocks the other. The lock lasts only until the commit below, which also
    flips the status to "processing" - from then on the status itself is the claim, so
    the long processing work runs outside any database transaction.
    """
    cutoff = datetime.now(UTC) - stale_after
    statement = (
        select(Document)
        .where(
            or_(
                Document.status == DocumentStatus.UPLOADED,
                # Recovery: a worker that died mid-way left the document "processing".
                and_(
                    Document.status == DocumentStatus.PROCESSING,
                    Document.processing_started_at < cutoff,
                ),
            )
        )
        .order_by(Document.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    document = (await session.execute(statement)).scalar_one_or_none()
    if document is None:
        await session.rollback()  # release the (empty) transaction
        return None

    document.status = DocumentStatus.PROCESSING
    document.processing_started_at = datetime.now(UTC)
    claimed = ClaimedDocument(document.id, document.storage_key, document.content_type)
    await session.commit()
    return claimed


async def _set_status(
    session: AsyncSession,
    document_id: object,
    status: DocumentStatus,
    error: str | None = None,
) -> None:
    # A plain UPDATE by id instead of modifying an ORM object: it works even after a
    # rollback, when ORM objects are expired.
    await session.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(status=status, error=error, processing_started_at=None)
    )
    await session.commit()


async def process_document(
    session: AsyncSession,
    storage: BlobStorage,
    embedder: Embedder,
    claimed: ClaimedDocument,
    settings: Settings,
) -> None:
    data = await storage.get(claimed.storage_key)
    # pdfplumber and python-docx are synchronous and CPU-bound. Running them directly
    # would freeze the event loop; a thread keeps the worker responsive.
    blocks = await asyncio.to_thread(parse_document, data, claimed.content_type)
    chunks = chunk_blocks(blocks, settings.chunk_max_chars, settings.chunk_overlap_chars)
    if not chunks:
        raise ValueError("no extractable text (a scanned PDF? OCR is not supported yet)")

    vectors = await embedder.embed_documents([chunk.text for chunk in chunks])

    # Everything below is ONE transaction: old chunks removed, new ones inserted, status
    # set. A reader sees either the old state or the new one, never a half-indexed document,
    # and re-processing a document cannot leave duplicate chunks behind.
    await session.execute(delete(Chunk).where(Chunk.document_id == claimed.id))
    session.add_all(
        Chunk(
            document_id=claimed.id,
            chunk_index=chunk.index,
            text=chunk.text,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            section_path=chunk.section_path,
            embedding=vector,
            embedding_model=embedder.model_name,
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    )
    await session.execute(
        update(Document)
        .where(Document.id == claimed.id)
        .values(status=DocumentStatus.INDEXED, error=None, processing_started_at=None)
    )
    await session.commit()


async def run_once(
    session: AsyncSession, storage: BlobStorage, embedder: Embedder, settings: Settings
) -> RunResult:
    claimed = await claim_next_document(session, timedelta(minutes=settings.worker_stale_minutes))
    if claimed is None:
        return RunResult.IDLE

    try:
        await process_document(session, storage, embedder, claimed, settings)
    except EmbedderUnavailableError as exc:
        # Not the document's fault: put it back in the queue and let the caller back off.
        await session.rollback()
        await _set_status(session, claimed.id, DocumentStatus.UPLOADED)
        logger.warning("Embedding service unavailable, document %s re-queued: %s", claimed.id, exc)
        return RunResult.DEFERRED
    except Exception as exc:  # any other error is recorded on the document
        await session.rollback()
        message = f"{type(exc).__name__}: {exc}"[:1000]
        await _set_status(session, claimed.id, DocumentStatus.FAILED, message)
        logger.error("Document %s failed: %s", claimed.id, message)
        return RunResult.PROCESSED
    logger.info("Document %s indexed", claimed.id)
    return RunResult.PROCESSED


async def run_forever() -> None:
    settings = get_settings()
    storage = AzureBlobStorage(settings.azure_storage_connection_string, settings.blob_container)
    await storage.start()
    embedder = OllamaEmbedder(settings.ollama_base_url, settings.embedding_model, EMBEDDING_DIM)
    logger.info("Worker started (model %s)", settings.embedding_model)
    try:
        while True:
            # A fresh session per iteration: a session left in a bad state (for example
            # after a database error) cannot poison the next document.
            async with SessionLocal() as session:
                result = await run_once(session, storage, embedder, settings)
            if result is RunResult.IDLE:
                await asyncio.sleep(settings.worker_poll_seconds)
            elif result is RunResult.DEFERRED:
                await asyncio.sleep(settings.worker_backoff_seconds)
            # PROCESSED: loop again immediately, there may be more documents waiting.
    finally:
        await embedder.close()
        await storage.close()
        await engine.dispose()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
