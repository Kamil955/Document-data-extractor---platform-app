import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.base import EmbeddingError
from app.jobs.extraction import run_extraction_once
from app.jobs.result import RunResult
from app.llm.base import LLMUnavailableError
from app.models import Extraction, ExtractionStatus
from tests.fakes import FakeEmbedder, FakeLLM, UnavailableLLM
from tests.test_ask import add_document
from tests.test_extract import SETTINGS, reply_by_field, run_worker
from tests.test_templates import NDA

pytestmark = pytest.mark.integration  # needs Postgres with pgvector


async def start(client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder) -> dict:
    document = await add_document(db_session, embedder)
    template_id = (await client.post("/templates", json=NDA)).json()["id"]
    response = await client.post(
        f"/documents/{document.id}/extract", json={"template_id": template_id}
    )
    assert response.status_code == 202
    return response.json()


async def test_the_request_is_only_recorded_and_the_worker_does_the_work(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    started = await start(client, db_session, embedder)

    assert started["status"] == "pending" and started["total"] == 3
    assert started["results"] == [] and llm.calls == []  # nothing was asked of the model yet

    await run_worker(db_session, embedder, llm, [started["extraction_id"]])

    done = (await client.get(f"/extractions/{started['extraction_id']}")).json()
    assert done["status"] == "completed" and len(done["results"]) == 3
    assert len(llm.calls) == 3
    # Nothing is left to do, and the model's name is the one of the worker's model.
    assert await run_extraction_once(db_session, embedder, llm, SETTINGS) is RunResult.IDLE
    assert done["model"] == "fake-llm"


async def test_results_appear_field_by_field(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    started = await start(client, db_session, embedder)
    extraction_id = started["extraction_id"]
    seen: list[int] = []

    def respond(prompt: str) -> dict:
        # While the model works on one field, the fields before it are already saved: this
        # is what lets the screen show progress.
        seen.append(len(llm.calls))
        return reply_by_field(prompt)

    llm.response = respond
    await run_worker(db_session, embedder, llm, [extraction_id])

    assert seen == [1, 2, 3]
    stored = (await client.get(f"/extractions/{extraction_id}")).json()
    assert [r["key"] for r in stored["results"]] == ["term", "notice_days", "governing_law"]


async def test_a_dead_worker_is_replaced_and_finished_fields_are_kept(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    started = await start(client, db_session, embedder)
    extraction = await db_session.get(Extraction, uuid.UUID(started["extraction_id"]))
    # A worker finished the first field, then died: "running" with an old heartbeat.
    first = extraction.fields[0]
    extraction.results = [
        {
            "key": first["key"],
            "label": first["label"],
            "type": first["type"],
            "value": "kept",
            "found": True,
            "supported": True,
            "citations": [],
            "retrieved": [],
            "error": None,
        }
    ]
    extraction.status = ExtractionStatus.RUNNING
    extraction.started_at = datetime.now(UTC) - timedelta(minutes=SETTINGS.worker_stale_minutes + 1)
    await db_session.commit()

    await run_worker(db_session, embedder, llm, [started["extraction_id"]])

    done = (await client.get(f"/extractions/{started['extraction_id']}")).json()
    assert done["status"] == "completed" and len(done["results"]) == 3
    assert done["results"][0]["value"] == "kept"  # not asked again
    assert len(llm.calls) == 2  # only the two fields that were still missing


async def test_a_running_extraction_with_a_fresh_heartbeat_is_left_alone(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    started = await start(client, db_session, embedder)
    extraction = await db_session.get(Extraction, uuid.UUID(started["extraction_id"]))
    extraction.status = ExtractionStatus.RUNNING
    extraction.started_at = datetime.now(UTC)
    await db_session.commit()

    await run_worker(db_session, embedder, llm, [started["extraction_id"]])

    assert llm.calls == []  # another worker is busy with it


async def test_model_down_puts_the_job_back_and_keeps_finished_fields(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    started = await start(client, db_session, embedder)

    def respond(prompt: str) -> dict:
        if "Governing law" in prompt:
            raise LLMUnavailableError("Ollama is down (test)")
        return reply_by_field(prompt)

    llm.response = respond

    await run_extraction_once(db_session, embedder, llm, SETTINGS)

    stored = (await client.get(f"/extractions/{started['extraction_id']}")).json()
    assert stored["status"] == "pending"  # waiting for the model, not failed
    assert len(stored["results"]) == 2  # the two fields before the failing one are saved


async def test_an_unavailable_model_defers_the_job(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    started = await start(client, db_session, embedder)

    result = await run_extraction_once(db_session, embedder, UnavailableLLM(), SETTINGS)

    assert result is RunResult.DEFERRED
    assert (await client.get(f"/extractions/{started['extraction_id']}")).json()[
        "status"
    ] == "pending"


async def test_an_error_that_is_not_the_models_fault_fails_the_job(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    started = await start(client, db_session, embedder)

    async def reject(text: str) -> list[float]:
        raise EmbeddingError("input too long (test)")

    embedder.embed_query = reject  # type: ignore[method-assign]
    await run_worker(db_session, embedder, llm, [started["extraction_id"]])

    stored = (await client.get(f"/extractions/{started['extraction_id']}")).json()
    assert stored["status"] == "failed"
    assert "input too long" in stored["error"]


async def test_changes_wait_until_the_extraction_is_finished(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    started = await start(client, db_session, embedder)
    url = f"/extractions/{started['extraction_id']}"

    corrected = await client.patch(f"{url}/values/term", json={"value": "x"})
    filled = await client.post(f"{url}/fill", files={"file": ("a.docx", b"x", "application/zip")})

    assert corrected.status_code == 409 and filled.status_code == 409


async def test_a_document_lists_its_extractions_newest_first(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    started = await start(client, db_session, embedder)
    document_id = started["document_id"]
    second = await client.post(
        f"/documents/{document_id}/extract", json={"fields": [{"key": "a", "label": "A"}]}
    )
    # now() is fixed for the whole transaction of a test, so both rows would get the same
    # time. In real use every request is its own transaction.
    first = await db_session.get(Extraction, uuid.UUID(started["extraction_id"]))
    first.created_at -= timedelta(minutes=1)
    await db_session.commit()
    await run_worker(
        db_session, embedder, llm, [started["extraction_id"], second.json()["extraction_id"]]
    )

    listed = (await client.get(f"/documents/{document_id}/extractions")).json()

    assert [e["extraction_id"] for e in listed] == [
        second.json()["extraction_id"],
        started["extraction_id"],
    ]
    assert listed[0]["template_name"] is None and listed[0]["total"] == 1
    assert listed[1]["template_name"] == NDA["name"] and listed[1]["done"] == 3
    assert {e["status"] for e in listed} == {"completed"}
    assert (await client.get(f"/documents/{uuid.uuid4()}/extractions")).status_code == 404


async def test_deleting_the_template_does_not_break_a_waiting_job(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    started = await start(client, db_session, embedder)
    # Deleting the template while the job waits must not break it.
    await client.delete(f"/templates/{started['template_id']}")

    await run_worker(db_session, embedder, llm, [started["extraction_id"]])

    done = (await client.get(f"/extractions/{started['extraction_id']}")).json()
    assert done["status"] == "completed" and len(done["results"]) == 3  # fields were copied
