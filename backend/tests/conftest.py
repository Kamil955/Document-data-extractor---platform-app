from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.db import get_session
from app.main import app


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A session whose changes are rolled back after the test.

    Every test gets its own engine with NullPool. pytest-asyncio runs each test in a
    fresh event loop, and a pooled connection created in one loop breaks in another.
    """
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    async with engine.connect() as connection:
        outer = await connection.begin()
        # create_savepoint: session.commit() inside a test releases a SAVEPOINT only,
        # so the outer transaction can still be rolled back and the database stays clean.
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    # Route the app through the test session instead of the global engine.
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    # ASGITransport calls the app in-process: no real network, no running server.
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()
