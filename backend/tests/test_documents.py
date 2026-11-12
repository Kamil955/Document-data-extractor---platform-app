import io
import uuid
import zipfile

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.documents import DOCX_MIME, PDF_MIME
from app.core.config import Settings, get_settings
from app.main import app
from tests.fakes import InMemoryStorage

pytestmark = pytest.mark.integration  # these tests use the real Postgres

PDF_BYTES = b"%PDF-1.7\n%fake pdf body for tests\n"


def make_docx() -> bytes:
    """The smallest archive that passes our DOCX check (word/document.xml present)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")
    return buffer.getvalue()


async def upload(
    client: AsyncClient, name: str, data: bytes, mime: str = "application/octet-stream"
):
    return await client.post("/documents", files={"file": (name, data, mime)})


async def test_upload_pdf_stores_file_and_metadata(
    client: AsyncClient, storage: InMemoryStorage
) -> None:
    response = await upload(client, "umowa.pdf", PDF_BYTES)

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "umowa.pdf"
    assert body["content_type"] == PDF_MIME
    assert body["status"] == "uploaded"
    assert "storage_key" not in body  # an internal detail must not leak
    assert storage.blobs[f"documents/{body['id']}"][0] == PDF_BYTES


async def test_upload_docx(client: AsyncClient) -> None:
    response = await upload(client, "umowa.docx", make_docx())
    assert response.status_code == 201
    assert response.json()["content_type"] == DOCX_MIME


async def test_type_is_detected_from_content_not_from_client(client: AsyncClient) -> None:
    # Claims to be a PDF, is plain text.
    response = await upload(client, "evil.pdf", b"just some text", mime=PDF_MIME)
    assert response.status_code == 415


async def test_zip_without_word_document_is_rejected(client: AsyncClient) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "not a docx")
    response = await upload(client, "archive.docx", buffer.getvalue())
    assert response.status_code == 415


async def test_too_large_upload_is_rejected(client: AsyncClient, storage: InMemoryStorage) -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(max_upload_bytes=10)
    response = await upload(client, "umowa.pdf", PDF_BYTES)
    assert response.status_code == 413
    assert storage.blobs == {}


async def test_path_is_stripped_from_filename(client: AsyncClient) -> None:
    response = await upload(client, "C:\\Users\\kamil\\umowa.pdf", PDF_BYTES)
    assert response.json()["filename"] == "umowa.pdf"


async def test_download_returns_original_bytes(client: AsyncClient) -> None:
    created = (await upload(client, "umowa o dzieło.pdf", PDF_BYTES)).json()

    response = await client.get(f"/documents/{created['id']}/file")

    assert response.status_code == 200
    assert response.content == PDF_BYTES
    assert response.headers["content-type"] == PDF_MIME
    # Non-ASCII file name survives thanks to the RFC 5987 encoding.
    assert "filename*=UTF-8''umowa%20o%20dzie%C5%82o.pdf" in response.headers["content-disposition"]


async def test_unknown_document_returns_404(client: AsyncClient) -> None:
    missing = uuid.uuid4()
    assert (await client.get(f"/documents/{missing}")).status_code == 404
    assert (await client.get(f"/documents/{missing}/file")).status_code == 404


async def test_list_returns_uploaded_documents(client: AsyncClient) -> None:
    await upload(client, "a.pdf", PDF_BYTES)
    await upload(client, "b.pdf", PDF_BYTES)

    response = await client.get("/documents")

    assert response.status_code == 200
    # Subset check: the table may already contain other documents from manual use.
    assert {"a.pdf", "b.pdf"} <= {item["filename"] for item in response.json()}


async def test_blob_is_removed_when_database_commit_fails(
    client: AsyncClient,
    storage: InMemoryStorage,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def failing_commit() -> None:
        raise RuntimeError("database is down")

    monkeypatch.setattr(db_session, "commit", failing_commit)

    with pytest.raises(RuntimeError):
        await upload(client, "umowa.pdf", PDF_BYTES)

    # The compensation step must have deleted the file stored before the failure.
    assert storage.blobs == {}
