import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentStatus

pytestmark = pytest.mark.integration


async def test_document_roundtrip(db_session: AsyncSession) -> None:
    document = Document(
        filename="contract.pdf",
        content_type="application/pdf",
        storage_key="documents/contract.pdf",
    )
    db_session.add(document)
    await db_session.commit()

    loaded = (await db_session.execute(select(Document))).scalar_one()
    assert loaded.id == document.id
    # Defaults: status from Python, created_at from the database (server_default).
    assert loaded.status is DocumentStatus.UPLOADED
    assert loaded.created_at is not None
