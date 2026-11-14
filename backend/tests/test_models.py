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


async def test_chunks_are_deleted_with_their_document(db_session: AsyncSession) -> None:
    from sqlalchemy import delete, func, select

    from app.models import Chunk

    document = Document(filename="a.pdf", content_type="application/pdf", storage_key="k/a")
    db_session.add(document)
    await db_session.flush()
    db_session.add(
        Chunk(
            document_id=document.id,
            chunk_index=0,
            text="hello",
            embedding=[0.0] * 1024,
            embedding_model="test",
        )
    )
    await db_session.commit()

    # A plain DELETE: the cascade is done by the database (ON DELETE CASCADE).
    await db_session.execute(delete(Document).where(Document.id == document.id))
    await db_session.commit()

    # Count only this document's chunks: a developer's database may hold other chunks.
    remaining = (
        await db_session.execute(
            select(func.count()).select_from(Chunk).where(Chunk.document_id == document.id)
        )
    ).scalar_one()
    assert remaining == 0


async def test_nearest_chunk_by_cosine_distance(db_session: AsyncSession) -> None:
    from sqlalchemy import select

    from app.models import Chunk
    from tests.fakes import FakeEmbedder

    embedder = FakeEmbedder()
    texts = ["payment terms", "termination notice", "governing law"]
    vectors = await embedder.embed_documents(texts)
    document = Document(filename="a.pdf", content_type="application/pdf", storage_key="k/b")
    db_session.add(document)
    await db_session.flush()
    db_session.add_all(
        Chunk(
            document_id=document.id,
            chunk_index=i,
            text=text,
            embedding=vector,
            embedding_model="test",
        )
        for i, (text, vector) in enumerate(zip(texts, vectors, strict=True))
    )
    await db_session.commit()

    query_vector = await embedder.embed_query("termination notice")
    nearest = (
        await db_session.execute(
            select(Chunk.text)
            .where(Chunk.document_id == document.id)
            .order_by(Chunk.embedding.cosine_distance(query_vector))
            .limit(1)
        )
    ).scalar_one()

    assert nearest == "termination notice"
