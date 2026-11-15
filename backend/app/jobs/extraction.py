"""Background extraction: the worker takes a pending extraction and fills it in field by field."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.embeddings.base import Embedder, EmbedderUnavailableError
from app.jobs.result import RunResult
from app.llm.base import LLM, LLMUnavailableError
from app.models import Extraction, ExtractionStatus, FieldType
from app.retrieval.extract import FieldResult, FieldSpec, extract_field
from app.schemas import CitationOut, FieldResultOut, RetrievedOut

logger = logging.getLogger(__name__)


def field_result_json(result: FieldResult) -> dict[str, Any]:
    """A finished field as the plain JSON that is stored and returned by the API."""
    output = FieldResultOut(
        key=result.key,
        label=result.label,
        type=result.field_type,
        value=result.value,
        found=result.found,
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
        error=result.error,
    )
    # mode="json" turns UUIDs and enums into plain JSON values for the JSONB column.
    return output.model_dump(mode="json")


@dataclass(frozen=True)
class ClaimedExtraction:
    """What the worker needs, copied out of the ORM object (see ClaimedDocument for why)."""

    id: uuid.UUID
    document_id: uuid.UUID
    fields: list[dict[str, Any]]
    retrieval_limit: int
    results: list[dict[str, Any]]  # fields finished by a worker that died earlier


async def claim_next_extraction(
    session: AsyncSession, stale_after: timedelta, model_name: str
) -> ClaimedExtraction | None:
    """Take one extraction, the same way claim_next_document takes a document.

    FOR UPDATE SKIP LOCKED lets several workers share the queue without picking the same
    row. A "running" extraction whose heartbeat (started_at) is old belongs to a dead worker
    and is taken over; the fields it already finished are kept.
    """
    cutoff = datetime.now(UTC) - stale_after
    statement = (
        select(Extraction)
        .where(
            or_(
                Extraction.status == ExtractionStatus.PENDING,
                (Extraction.status == ExtractionStatus.RUNNING) & (Extraction.started_at < cutoff),
            )
        )
        .order_by(Extraction.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    extraction = (await session.execute(statement)).scalar_one_or_none()
    if extraction is None:
        await session.rollback()
        return None

    extraction.status = ExtractionStatus.RUNNING
    extraction.started_at = datetime.now(UTC)
    extraction.model = model_name  # the model that really does the work
    claimed = ClaimedExtraction(
        extraction.id,
        extraction.document_id,
        list(extraction.fields),
        extraction.retrieval_limit,
        list(extraction.results),
    )
    await session.commit()
    return claimed


async def _update(session: AsyncSession, extraction_id: uuid.UUID, **values: Any) -> None:
    # A plain UPDATE by id: it works after a rollback too, and does nothing when the document
    # (and with it the extraction) was deleted in the meantime.
    await session.execute(update(Extraction).where(Extraction.id == extraction_id).values(**values))
    await session.commit()


async def process_extraction(
    session: AsyncSession, embedder: Embedder, llm: LLM, claimed: ClaimedExtraction
) -> None:
    results = list(claimed.results)
    # Resume after the fields that are already done (a worker that died mid-way).
    for item in claimed.fields[len(results) :]:
        spec = FieldSpec(item["key"], item["label"], item["description"], FieldType(item["type"]))
        # Sequential on purpose: one local model on one GPU serves one request at a time.
        result = await extract_field(
            session,
            embedder,
            llm,
            spec,
            document_id=claimed.document_id,
            limit=claimed.retrieval_limit,
        )
        results = [*results, field_result_json(result)]
        # Saved after every field: the screen shows progress, and a crash loses one field only.
        # started_at doubles as the heartbeat that tells other workers this one is alive.
        await _update(session, claimed.id, results=results, started_at=datetime.now(UTC))
    await _update(session, claimed.id, status=ExtractionStatus.COMPLETED, started_at=None)


async def run_extraction_once(
    session: AsyncSession, embedder: Embedder, llm: LLM, settings: Settings
) -> RunResult:
    """Run one waiting extraction (if any), like run_once does for documents."""
    claimed = await claim_next_extraction(
        session, timedelta(minutes=settings.worker_stale_minutes), llm.model_name
    )
    if claimed is None:
        return RunResult.IDLE
    try:
        await process_extraction(session, embedder, llm, claimed)
    except (EmbedderUnavailableError, LLMUnavailableError) as exc:
        # Not the extraction's fault: back to the queue, finished fields are kept.
        await session.rollback()
        await _update(session, claimed.id, status=ExtractionStatus.PENDING, started_at=None)
        logger.warning("Model unavailable, extraction %s re-queued: %s", claimed.id, exc)
        return RunResult.DEFERRED
    except Exception as exc:  # recorded on the extraction, shown to the user
        await session.rollback()
        message = f"{type(exc).__name__}: {exc}"[:1000]
        await _update(
            session, claimed.id, status=ExtractionStatus.FAILED, error=message, started_at=None
        )
        logger.error("Extraction %s failed: %s", claimed.id, message)
        return RunResult.PROCESSED
    logger.info("Extraction %s completed", claimed.id)
    return RunResult.PROCESSED
