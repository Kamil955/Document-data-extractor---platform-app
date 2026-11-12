import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.content_types import DOCX_MIME, PDF_MIME
from app.ingestion.worker import RunResult, claim_next_document, run_once
from app.models import Chunk, Document, DocumentStatus
from tests.fakes import FakeEmbedder, InMemoryStorage, UnavailableEmbedder
from tests.files import make_blank_pdf, make_docx, make_pdf

pytestmark = pytest.mark.integration  # needs the real Postgres with pgvector

SETTINGS = Settings(chunk_max_chars=300, chunk_overlap_chars=60)


@pytest.fixture(autouse=True)
async def empty_queue(db_session: AsyncSession) -> None:
    # The worker takes ANY waiting document, so rows left in a developer's database (for
    # example a manually uploaded file) would be picked up instead of the test's own one.
    # The DELETE is rolled back together with the rest of the test's transaction.
    await db_session.execute(delete(Document))


async def add_document(
    session: AsyncSession,
    storage: InMemoryStorage,
    data: bytes,
    content_type: str = PDF_MIME,
    **overrides: object,
) -> Document:
    # The id is normally generated on INSERT, so set it up front to build a unique storage key.
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        filename="contract",
        content_type=content_type,
        storage_key=f"documents/{document_id}",
        **overrides,
    )
    await storage.put(document.storage_key, data, content_type)
    session.add(document)
    await session.commit()
    return document


async def count_chunks(session: AsyncSession, document: Document) -> int:
    query = select(func.count()).select_from(Chunk).where(Chunk.document_id == document.id)
    return (await session.execute(query)).scalar_one()


def contract_pdf() -> bytes:
    body = [f"Clause text number {i} about payment and delivery." for i in range(25)]
    return make_pdf([["1. Definitions", *body[:12]], ["2. Payment", *body[12:]]])


async def test_pdf_is_parsed_chunked_embedded_and_stored(
    db_session: AsyncSession, storage: InMemoryStorage
) -> None:
    document = await add_document(db_session, storage, contract_pdf())
    embedder = FakeEmbedder()

    result = await run_once(db_session, storage, embedder, SETTINGS)

    assert result is RunResult.PROCESSED
    await db_session.refresh(document)
    assert document.status is DocumentStatus.INDEXED
    assert document.error is None
    assert document.processing_started_at is None

    chunks = (
        (
            await db_session.execute(
                select(Chunk).where(Chunk.document_id == document.id).order_by(Chunk.chunk_index)
            )
        )
        .scalars()
        .all()
    )
    assert len(chunks) > 2
    assert [c.chunk_index for c in chunks] == list(range(len(chunks)))
    assert all(len(c.embedding) == 1024 for c in chunks)
    assert {c.embedding_model for c in chunks} == {"fake-embedder"}
    assert {c.section_path for c in chunks} == {"1. Definitions", "2. Payment"}
    assert chunks[0].page_start == 1
    assert chunks[-1].page_end == 2
    # The embedder received exactly the texts that were stored.
    assert [c.text for c in chunks] == embedder.calls[0]


async def test_docx_is_indexed_without_page_numbers(
    db_session: AsyncSession, storage: InMemoryStorage
) -> None:
    document = await add_document(db_session, storage, make_docx(), DOCX_MIME)

    await run_once(db_session, storage, FakeEmbedder(), SETTINGS)

    await db_session.refresh(document)
    assert document.status is DocumentStatus.INDEXED
    chunk = (await db_session.execute(select(Chunk).limit(1))).scalars().first()
    assert chunk is not None and chunk.page_start is None


async def test_idle_when_nothing_is_waiting(
    db_session: AsyncSession, storage: InMemoryStorage
) -> None:
    # Documents that are not waiting must be left alone.
    await add_document(db_session, storage, contract_pdf(), status=DocumentStatus.INDEXED)
    assert await run_once(db_session, storage, FakeEmbedder(), SETTINGS) is RunResult.IDLE


async def test_unreadable_file_fails_with_a_message(
    db_session: AsyncSession, storage: InMemoryStorage
) -> None:
    document = await add_document(db_session, storage, b"%PDF-1.7 broken")

    result = await run_once(db_session, storage, FakeEmbedder(), SETTINGS)

    assert result is RunResult.PROCESSED  # handled: the queue is not stuck
    await db_session.refresh(document)
    assert document.status is DocumentStatus.FAILED
    assert "cannot read PDF" in document.error
    assert await count_chunks(db_session, document) == 0


async def test_scanned_pdf_fails_with_a_clear_reason(
    db_session: AsyncSession, storage: InMemoryStorage
) -> None:
    document = await add_document(db_session, storage, make_blank_pdf())

    await run_once(db_session, storage, FakeEmbedder(), SETTINGS)

    await db_session.refresh(document)
    assert document.status is DocumentStatus.FAILED
    assert "no extractable text" in document.error


async def test_missing_blob_fails_the_document(
    db_session: AsyncSession, storage: InMemoryStorage
) -> None:
    document = await add_document(db_session, storage, contract_pdf())
    storage.blobs.clear()

    await run_once(db_session, storage, FakeEmbedder(), SETTINGS)

    await db_session.refresh(document)
    assert document.status is DocumentStatus.FAILED


async def test_unavailable_embedder_requeues_instead_of_failing(
    db_session: AsyncSession, storage: InMemoryStorage
) -> None:
    document = await add_document(db_session, storage, contract_pdf())

    result = await run_once(db_session, storage, UnavailableEmbedder(), SETTINGS)

    assert result is RunResult.DEFERRED
    await db_session.refresh(document)
    assert document.status is DocumentStatus.UPLOADED  # waiting, not failed
    assert document.error is None
    assert await count_chunks(db_session, document) == 0

    # Once the service is back, the same document is processed normally.
    assert await run_once(db_session, storage, FakeEmbedder(), SETTINGS) is RunResult.PROCESSED
    await db_session.refresh(document)
    assert document.status is DocumentStatus.INDEXED


async def test_reprocessing_replaces_chunks_without_duplicates(
    db_session: AsyncSession, storage: InMemoryStorage
) -> None:
    document = await add_document(db_session, storage, contract_pdf())
    await run_once(db_session, storage, FakeEmbedder(), SETTINGS)
    first_count = await count_chunks(db_session, document)

    document.status = DocumentStatus.UPLOADED  # what the /reprocess endpoint does
    await db_session.commit()
    await run_once(db_session, storage, FakeEmbedder(), SETTINGS)

    assert await count_chunks(db_session, document) == first_count


async def test_abandoned_processing_document_is_reclaimed(
    db_session: AsyncSession, storage: InMemoryStorage
) -> None:
    long_ago = datetime.now(UTC) - timedelta(hours=1)
    document = await add_document(
        db_session,
        storage,
        contract_pdf(),
        status=DocumentStatus.PROCESSING,
        processing_started_at=long_ago,
    )

    result = await run_once(db_session, storage, FakeEmbedder(), SETTINGS)

    assert result is RunResult.PROCESSED
    await db_session.refresh(document)
    assert document.status is DocumentStatus.INDEXED


async def test_document_being_processed_right_now_is_not_taken(
    db_session: AsyncSession, storage: InMemoryStorage
) -> None:
    await add_document(
        db_session,
        storage,
        contract_pdf(),
        status=DocumentStatus.PROCESSING,
        processing_started_at=datetime.now(UTC),
    )
    assert await claim_next_document(db_session, timedelta(minutes=10)) is None


async def test_oldest_document_is_processed_first(
    db_session: AsyncSession, storage: InMemoryStorage
) -> None:
    older = await add_document(
        db_session, storage, contract_pdf(), created_at=datetime.now(UTC) - timedelta(hours=2)
    )
    newer = await add_document(db_session, storage, contract_pdf())

    claimed = await claim_next_document(db_session, timedelta(minutes=10))

    assert claimed is not None and claimed.id == older.id
    assert claimed.id != newer.id
