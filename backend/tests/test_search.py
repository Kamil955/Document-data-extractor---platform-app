import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_embedder
from app.main import app
from app.models import Chunk, Document
from tests.fakes import FakeEmbedder, UnavailableEmbedder

pytestmark = pytest.mark.integration  # needs Postgres with pgvector

TEXTS = ["payment is due in 30 days", "either party may terminate", "governed by English law"]


async def add_document(
    session: AsyncSession, embedder: FakeEmbedder, texts: list[str], model: str | None = None
) -> Document:
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        filename=f"{document_id}.pdf",
        content_type="application/pdf",
        storage_key=f"documents/{document_id}",
    )
    session.add(document)
    await session.flush()
    vectors = await embedder.embed_documents(texts)
    session.add_all(
        Chunk(
            document_id=document.id,
            chunk_index=i,
            text=text,
            page_start=i + 1,
            page_end=i + 1,
            section_path=f"{i + 1}. Section",
            embedding=vector,
            embedding_model=model or embedder.model_name,
        )
        for i, (text, vector) in enumerate(zip(texts, vectors, strict=True))
    )
    await session.commit()
    return document


async def test_best_match_comes_first(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    document = await add_document(db_session, embedder, TEXTS)

    response = await client.post(
        "/search", json={"query": "either party may terminate", "document_id": str(document.id)}
    )

    assert response.status_code == 200
    hits = response.json()
    assert [h["text"] for h in hits][0] == "either party may terminate"
    assert hits[0]["score"] == pytest.approx(1.0, abs=1e-4)  # identical text, same vector
    assert hits[0]["score"] > hits[1]["score"]
    assert hits[0]["page_start"] == 2
    assert hits[0]["section_path"] == "2. Section"
    assert hits[0]["filename"] == document.filename
    assert "embedding" not in hits[0]


async def test_limit_is_respected(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    document = await add_document(db_session, embedder, TEXTS)

    response = await client.post(
        "/search", json={"query": "anything", "limit": 2, "document_id": str(document.id)}
    )

    assert len(response.json()) == 2


async def test_search_can_be_limited_to_one_document(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    first = await add_document(db_session, embedder, TEXTS)
    second = await add_document(db_session, embedder, TEXTS)

    response = await client.post(
        "/search", json={"query": TEXTS[0], "limit": 20, "document_id": str(second.id)}
    )

    document_ids = {h["document_id"] for h in response.json()}
    assert document_ids == {str(second.id)}
    assert str(first.id) not in document_ids


async def test_chunks_from_another_model_are_ignored(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    document = await add_document(db_session, embedder, TEXTS, model="some-other-model")

    response = await client.post(
        "/search", json={"query": TEXTS[0], "document_id": str(document.id)}
    )

    assert response.json() == []  # vectors of different models must never be compared


async def test_empty_query_is_rejected(client: AsyncClient) -> None:
    assert (await client.post("/search", json={"query": ""})).status_code == 422
    assert (await client.post("/search", json={"query": "x", "limit": 0})).status_code == 422


async def test_embedding_service_down_gives_503(client: AsyncClient) -> None:
    app.dependency_overrides[get_embedder] = lambda: UnavailableEmbedder()

    response = await client.post("/search", json={"query": "anything"})

    assert response.status_code == 503


def test_keyword_query_keeps_words_and_cannot_inject_syntax() -> None:
    from app.retrieval.search import keyword_query

    assert (
        keyword_query("Payment terms, payment: how is it PAID?") == "payment | terms | how | paid"
    )
    # Characters with a meaning in tsquery syntax are dropped, not passed on.
    assert keyword_query("a' | !b & (c):*") is None
    assert keyword_query("---") is None


async def test_hybrid_finds_an_exact_word_that_meaning_alone_ranks_low(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    # The fake embedder knows no meaning: vector order is arbitrary. Only the keyword half can
    # know that "payment" is the word the query is about, so hybrid must put that chunk first.
    document = await add_document(db_session, embedder, TEXTS)

    response = await client.post(
        "/search",
        json={"query": "payment", "limit": 3, "document_id": str(document.id), "mode": "hybrid"},
    )

    assert response.json()[0]["text"] == "payment is due in 30 days"


async def test_vector_mode_does_not_use_keywords(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    document = await add_document(db_session, embedder, TEXTS)
    texts = {}
    for mode in ("vector", "hybrid"):
        response = await client.post(
            "/search",
            json={"query": "payment", "limit": 3, "document_id": str(document.id), "mode": mode},
        )
        texts[mode] = [h["text"] for h in response.json()]

    # Same candidates, so the difference between the two modes is only the order, and the
    # score of every hit is still a cosine similarity.
    assert sorted(texts["vector"]) == sorted(texts["hybrid"])
    assert texts["hybrid"][0] == "payment is due in 30 days"


async def test_query_with_special_characters_does_not_break_hybrid_search(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    document = await add_document(db_session, embedder, TEXTS)

    response = await client.post(
        "/search",
        json={
            "query": "payment' | !terms & (x):*",
            "document_id": str(document.id),
            "mode": "hybrid",
        },
    )

    assert response.status_code == 200


async def test_unknown_mode_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/search", json={"query": "x", "mode": "magic"})

    assert response.status_code == 422
