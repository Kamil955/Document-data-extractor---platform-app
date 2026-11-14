import io
import uuid

import pytest
from docx import Document
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_types import DOCX_MIME
from tests.fakes import FakeEmbedder, FakeLLM
from tests.test_ask import add_document
from tests.test_extract import reply_by_field
from tests.test_templates import NDA

pytestmark = pytest.mark.integration  # needs Postgres with pgvector


def make_template_docx() -> bytes:
    document = Document()
    document.add_paragraph("Governing law: {{governing_law}}")
    document.add_paragraph("Notice: {{notice_days}}; term: {{term}}; other: {{mystery}}")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


async def extract(client: AsyncClient, db_session, embedder, llm: FakeLLM) -> dict:
    document = await add_document(db_session, embedder)
    template_id = (await client.post("/templates", json=NDA)).json()["id"]
    llm.response = reply_by_field
    response = await client.post(
        f"/documents/{document.id}/extract", json={"template_id": template_id}
    )
    assert response.status_code == 200
    return response.json()


async def test_extraction_is_saved_and_can_be_read_again(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    created = await extract(client, db_session, embedder, llm)

    fetched = await client.get(f"/extractions/{created['extraction_id']}")

    assert fetched.status_code == 200
    assert fetched.json() == created  # nothing is lost on the way through the database
    assert (await client.get(f"/extractions/{uuid.uuid4()}")).status_code == 404


async def test_fill_a_docx_from_a_saved_extraction(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    created = await extract(client, db_session, embedder, llm)

    response = await client.post(
        f"/extractions/{created['extraction_id']}/fill",
        files={"file": ("summary.docx", make_template_docx(), DOCX_MIME)},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == DOCX_MIME
    assert "filled-summary.docx" in response.headers["content-disposition"]
    assert response.headers["x-fill-filled"] == "2"  # governing_law, notice_days
    assert response.headers["x-fill-missing"] == "term"  # the model found nothing
    assert response.headers["x-fill-unknown"] == "mystery"  # not a field of the template
    text = [p.text for p in Document(io.BytesIO(response.content)).paragraphs]
    assert text[0] == "Governing law: State of Washington"
    assert (
        text[1]
        == "Notice: 10 business days; term: [not found: Term of the agreement]; other: {{mystery}}"
    )


async def test_fill_rejects_a_file_that_is_not_docx(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    created = await extract(client, db_session, embedder, llm)

    response = await client.post(
        f"/extractions/{created['extraction_id']}/fill",
        files={"file": ("x.docx", b"%PDF-1.7 not a word file", "application/pdf")},
    )

    assert response.status_code == 415


async def test_fill_unknown_extraction_is_404(client: AsyncClient) -> None:
    response = await client.post(
        f"/extractions/{uuid.uuid4()}/fill",
        files={"file": ("x.docx", make_template_docx(), DOCX_MIME)},
    )

    assert response.status_code == 404


async def test_deleting_the_template_keeps_the_extraction(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    created = await extract(client, db_session, embedder, llm)

    await client.delete(f"/templates/{created['template_id']}")

    fetched = (await client.get(f"/extractions/{created['extraction_id']}")).json()
    assert fetched["template_id"] is None and len(fetched["results"]) == 3


async def test_deleting_the_document_deletes_its_extractions(
    client: AsyncClient, db_session: AsyncSession, embedder: FakeEmbedder, llm: FakeLLM
) -> None:
    created = await extract(client, db_session, embedder, llm)

    await client.delete(f"/documents/{created['document_id']}")

    assert (await client.get(f"/extractions/{created['extraction_id']}")).status_code == 404
