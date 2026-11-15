import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.jobs.extraction import run_extraction_once
from app.jobs.result import RunResult
from app.llm.base import LLMError
from app.models import DocumentStatus, Extraction, ExtractionStatus
from tests.fakes import FakeEmbedder, FakeLLM
from tests.test_ask import TEXTS, add_document, excerpt_number
from tests.test_templates import NDA

pytestmark = pytest.mark.integration  # needs Postgres with pgvector

SETTINGS = Settings()


async def run_worker(
    db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM, keep: list[str]
) -> None:
    """Run the extraction jobs the way the worker does, until the queue is empty.

    The worker takes ANY waiting job, so rows left in a developer's database would be picked
    up instead of the test's own. Other unfinished rows are removed first (the DELETE is rolled
    back with the rest of the test's transaction).
    """
    await db_session.execute(
        delete(Extraction).where(
            Extraction.id.not_in([uuid.UUID(k) for k in keep]),
            Extraction.status.in_([ExtractionStatus.PENDING, ExtractionStatus.RUNNING]),
        )
    )
    for _ in range(20):  # a bound, so a bug cannot make a test loop forever
        if await run_extraction_once(db_session, embedder, llm, SETTINGS) is RunResult.IDLE:
            return


async def extract_now(
    client: AsyncClient,
    db_session: AsyncSession,
    embedder: FakeEmbedder,
    llm: FakeLLM,
    document_id: uuid.UUID,
    body: dict,
) -> dict:
    """Start an extraction, let the worker finish it and return the stored result."""
    started = await client.post(f"/documents/{document_id}/extract", json=body)
    assert started.status_code == 202
    extraction_id = started.json()["extraction_id"]
    await run_worker(db_session, embedder, llm, [extraction_id])
    return (await client.get(f"/extractions/{extraction_id}")).json()


def reply_by_field(prompt: str) -> dict:
    """A fake model that answers per field: finds notice and law, 'does not know' the rest."""
    if "Termination notice" in prompt:
        n = excerpt_number(prompt, "ten (10) business days")
        return {
            "found": True,
            "answer": "10 business days [1]",
            "citations": [{"excerpt": n, "quote": "ten (10) business days written notice"}],
        }
    if "Governing law" in prompt:
        n = excerpt_number(prompt, "State of Washington")
        return {
            "found": True,
            "answer": "State of Washington",
            "citations": [{"excerpt": n, "quote": "the laws of the State of Washington"}],
        }
    return {"found": False, "answer": "", "citations": []}


async def test_extract_with_a_stored_template(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)
    template_id = (await client.post("/templates", json=NDA)).json()["id"]
    llm.response = reply_by_field

    body = await extract_now(
        client, db_session, embedder, llm, document.id, {"template_id": template_id}
    )

    assert body["status"] == "completed" and body["total"] == 3
    assert body["template_id"] == template_id and body["model"] == "fake-llm"
    by_key = {r["key"]: r for r in body["results"]}
    assert list(by_key) == ["term", "notice_days", "governing_law"]  # template order kept

    notice = by_key["notice_days"]
    assert notice["value"] == "10 business days"  # the "[1]" marker is stripped
    assert notice["supported"] and notice["citations"][0]["verified"]
    assert notice["citations"][0]["page_start"] == 2
    assert by_key["governing_law"]["value"] == "State of Washington"
    # The chunks the model saw are part of the result, so a missing value can be debugged.
    assert len(by_key["governing_law"]["retrieved"]) == 3
    # A field the document does not state is reported as not found, not guessed.
    assert by_key["term"]["found"] is False and by_key["term"]["citations"] == []


async def test_prompt_describes_the_field_and_its_type(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)

    await extract_now(
        client,
        db_session,
        embedder,
        llm,
        document.id,
        {
            "fields": [
                {
                    "key": "notice",
                    "label": "Termination notice",
                    "description": "days of written notice",
                    "type": "number",
                }
            ]
        },
    )

    _, user_prompt, _ = llm.calls[0]
    assert "about 'Termination notice' (days of written notice)" in user_prompt
    assert "Answer with a number" in user_prompt


async def test_each_field_is_searched_by_its_own_short_query(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    # The embedder fake is seeded by text, so the first excerpt is the chunk whose text
    # equals the search query. Using the long instruction as the query would never match.
    document = await add_document(db_session, embedder)

    await extract_now(
        client,
        db_session,
        embedder,
        llm,
        document.id,
        {"fields": [{"key": "law", "label": TEXTS[2]}]},
    )

    _, user_prompt, _ = llm.calls[0]
    assert f"[1] (page 3, section 3. Section)\n{TEXTS[2]}" in user_prompt


async def test_request_needs_exactly_one_source_of_fields(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    document = await add_document(db_session, embedder)
    url = f"/documents/{document.id}/extract"
    field = {"key": "a", "label": "A"}

    assert (await client.post(url, json={})).status_code == 422
    both = {"template_id": str(uuid.uuid4()), "fields": [field]}
    assert (await client.post(url, json=both)).status_code == 422


async def test_unknown_document_template_and_unready_document(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    field = {"fields": [{"key": "a", "label": "A"}]}
    assert (await client.post(f"/documents/{uuid.uuid4()}/extract", json=field)).status_code == 404

    document = await add_document(db_session, embedder)
    missing = {"template_id": str(uuid.uuid4())}
    assert (await client.post(f"/documents/{document.id}/extract", json=missing)).status_code == 404

    document.status = DocumentStatus.PROCESSING
    await db_session.commit()
    response = await client.post(f"/documents/{document.id}/extract", json=field)
    assert response.status_code == 409


async def test_one_unusable_reply_does_not_lose_the_other_fields(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)

    def respond(prompt: str) -> dict:
        if "'Broken'" in prompt:
            raise LLMError("not JSON")
        return reply_by_field(prompt)

    llm.response = respond

    body = await extract_now(
        client,
        db_session,
        embedder,
        llm,
        document.id,
        {
            "fields": [
                {"key": "broken", "label": "Broken"},
                {"key": "law", "label": "Governing law"},
            ]
        },
    )

    assert body["status"] == "completed"  # a bad reply is recorded on its field, not the job
    results = {r["key"]: r for r in body["results"]}
    assert results["broken"]["error"] == "not JSON" and results["broken"]["found"] is False
    assert results["law"]["supported"] is True and results["law"]["error"] is None


async def test_boolean_field_must_not_be_inferred_from_silence(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)

    await extract_now(
        client,
        db_session,
        embedder,
        llm,
        document.id,
        {"fields": [{"key": "nc", "label": "Non-compete", "type": "boolean"}]},
    )

    _, user_prompt, _ = llm.calls[0]
    assert "explicitly" in user_prompt and "not address it" in user_prompt


async def test_each_field_costs_exactly_one_model_call(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)

    await extract_now(
        client,
        db_session,
        embedder,
        llm,
        document.id,
        {"fields": [{"key": "x", "label": "Anything"}]},
    )

    assert len(llm.calls) == 1


async def test_a_negative_boolean_is_never_marked_verified(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)
    llm.response = lambda prompt: {
        "found": True,
        "answer": "No",
        "citations": [
            {"excerpt": excerpt_number(prompt, "ten (10)"), "quote": "ten (10) business days"}
        ],
    }
    fields = [
        {"key": "nc", "label": "Non-compete", "type": "boolean"},
        {"key": "txt", "label": "Notice", "type": "text"},
    ]

    results = (
        await extract_now(client, db_session, embedder, llm, document.id, {"fields": fields})
    )["results"]

    by_key = {r["key"]: r for r in results}
    # The quote is real, but a quote cannot prove that a clause does not exist.
    assert by_key["nc"]["found"] is True and by_key["nc"]["supported"] is False
    assert by_key["txt"]["value"] == "No" and by_key["txt"]["supported"] is True
