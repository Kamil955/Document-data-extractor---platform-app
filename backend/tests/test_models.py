import pytest
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

    # refresh() reloads the row from the database, so this checks what Postgres really
    # stored. It does not assume the table is empty: other rows may exist (for example
    # documents uploaded by hand while developing).
    await db_session.refresh(document)

    # Defaults: status from Python, created_at from the database (server_default).
    assert document.status is DocumentStatus.UPLOADED
    assert document.created_at is not None
