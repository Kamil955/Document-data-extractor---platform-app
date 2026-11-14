import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_llm
from app.main import app
from app.models import Chunk, Document, DocumentStatus
from tests.fakes import FakeEmbedder, FakeLLM, UnavailableLLM

pytestmark = pytest.mark.integration  # needs Postgres with pgvector

TEXTS = [
    "This Agreement shall remain in effect for one (1) year from the Effective Date.",
    "Either party may terminate on ten (10) business days written notice.",
    "This Agreement is governed by the laws of the State of Washington.",
]


async def add_document(session: AsyncSession, embedder: FakeEmbedder) -> Document:
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        filename="nda.pdf",
        content_type="application/pdf",
        storage_key=f"documents/{document_id}",
        status=DocumentStatus.INDEXED,  # extraction accepts only indexed documents
    )
    session.add(document)
    await session.flush()
    vectors = await embedder.embed_documents(TEXTS)
    session.add_all(
        Chunk(
            document_id=document.id,
            chunk_index=i,
            text=text,
            page_start=i + 1,
            page_end=i + 1,
            section_path=f"{i + 1}. Section",
            embedding=vector,
            embedding_model=embedder.model_name,
        )
        for i, (text, vector) in enumerate(zip(TEXTS, vectors, strict=True))
    )
    await session.commit()
    return document


def excerpt_number(prompt: str, fragment: str) -> int:
    """Which excerpt [n] of the prompt contains the fragment (the best match is excerpt 1)."""
    for number in range(1, 4):
        start = prompt.index(f"[{number}]")
        end = prompt.find(f"[{number + 1}]", start)
        if fragment in prompt[start : end if end != -1 else None]:
            return number
    raise AssertionError(f"{fragment!r} not in the prompt")


async def ask(client: AsyncClient, document: Document, question: str = TEXTS[1]):
    return await client.post("/ask", json={"question": question, "document_id": str(document.id)})


async def test_supported_answer_with_verified_citation(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)

    def respond(prompt: str) -> dict:
        n = excerpt_number(prompt, "ten (10) business days")
        return {
            "found": True,
            "answer": "Ten (10) business days.",
            # Line breaks and case differ from the source: still the same quote.
            "citations": [{"excerpt": n, "quote": "TEN (10) business\ndays written notice"}],
        }

    llm.response = respond

    response = await ask(client, document)

    assert response.status_code == 200
    body = response.json()
    assert body["found"] and body["supported"]
    assert body["answer"] == "Ten (10) business days."
    citation = body["citations"][0]
    assert citation["verified"] is True
    assert citation["page_start"] == 2 and citation["section_path"] == "2. Section"
    assert citation["filename"] == "nda.pdf"
    assert body["model"] == "fake-llm"
    assert len(body["retrieved"]) == 3


async def test_invented_quote_is_flagged_not_trusted(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)
    llm.response = {
        "found": True,
        "answer": "Thirty days.",
        "citations": [{"excerpt": 1, "quote": "terminate on thirty days notice"}],
    }

    body = (await ask(client, document)).json()

    assert body["found"] is True
    assert body["supported"] is False  # the quote does not occur in the source
    assert body["citations"][0]["verified"] is False


async def test_citation_of_a_nonexistent_excerpt_is_dropped(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)
    llm.response = {
        "found": True,
        "answer": "Something.",
        "citations": [{"excerpt": 99, "quote": "whatever"}, {"excerpt": 0, "quote": "x"}],
    }

    body = (await ask(client, document)).json()

    assert body["citations"] == []
    assert body["supported"] is False


async def test_not_found_answer_has_no_citations(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)
    llm.response = {
        "found": False,
        "answer": "I made this up",
        "citations": [{"excerpt": 1, "quote": "x"}],
    }

    body = (await ask(client, document)).json()

    assert body["found"] is False
    assert body["answer"] == ""  # an answer the model says it cannot support is not shown
    assert body["citations"] == [] and body["supported"] is False


async def test_prompt_contains_numbered_excerpts_with_page_and_section(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)

    # The fake embedder only matches identical text, so the question repeats the chunk text:
    # that chunk is then the best match and becomes excerpt [1].
    await ask(client, document, question=TEXTS[1])

    system, user, schema = llm.calls[0]
    assert "ONLY the numbered excerpts" in system
    assert "[1] (page 2, section 2. Section)" in user  # the best match comes first
    assert TEXTS[1] in user
    assert user.rstrip().endswith(f"Question: {TEXTS[1]}")
    assert "found" in schema["required"]


async def test_no_indexed_chunks_means_no_model_call(client: AsyncClient, llm: FakeLLM) -> None:
    response = await client.post(
        "/ask", json={"question": "anything", "document_id": str(uuid.uuid4())}
    )

    assert response.json()["found"] is False
    assert llm.calls == []  # nothing to read, so the model is not asked (and cannot guess)


async def test_model_down_gives_503(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder
) -> None:
    document = await add_document(db_session, embedder)
    app.dependency_overrides[get_llm] = lambda: UnavailableLLM()

    assert (await ask(client, document)).status_code == 503


async def test_empty_question_is_rejected(client: AsyncClient) -> None:
    assert (await client.post("/ask", json={"question": ""})).status_code == 422


async def test_retry_when_the_first_quote_is_not_verbatim(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)

    def respond(prompt: str) -> dict:
        n = excerpt_number(prompt, "ten (10) business days")
        # The first reply paraphrases the quote; after the retry note it copies it exactly.
        quote = "ten (10) business days written notice" if "word for word" in prompt else "10 days"
        return {
            "found": True,
            "answer": "10 business days",
            "citations": [{"excerpt": n, "quote": quote}],
        }

    llm.response = respond

    body = (await ask(client, document)).json()

    assert len(llm.calls) == 2
    assert body["supported"] is True and body["citations"][0]["verified"] is True


async def test_no_retry_when_the_quote_is_already_verified(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)
    llm.response = lambda prompt: {
        "found": True,
        "answer": "Washington",
        "citations": [
            {"excerpt": excerpt_number(prompt, "Washington"), "quote": "State of Washington"}
        ],
    }

    await ask(client, document)

    assert len(llm.calls) == 1


async def test_failed_retry_keeps_the_first_answer_flagged(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)
    llm.response = {
        "found": True,
        "answer": "Thirty days.",
        "citations": [{"excerpt": 1, "quote": "never in the text"}],
    }

    body = (await ask(client, document)).json()

    assert len(llm.calls) == 2  # exactly one retry, not a loop
    assert body["found"] is True and body["supported"] is False
    assert body["answer"] == "Thirty days."


async def test_excerpt_numbers_are_removed_from_the_answer(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    document = await add_document(db_session, embedder)
    llm.response = lambda prompt: {
        "found": True,
        "answer": "Ten business days [1], by written notice [2].",
        "citations": [
            {"excerpt": excerpt_number(prompt, "ten (10)"), "quote": "ten (10) business days"}
        ],
    }

    body = (await ask(client, document)).json()

    assert body["answer"] == "Ten business days, by written notice."
