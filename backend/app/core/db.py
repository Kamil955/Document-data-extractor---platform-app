from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

# Creating the engine does not open a connection; the first query does.
# pool_pre_ping checks a pooled connection before use and replaces it if the
# database restarted in the meantime.
engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)

# expire_on_commit=False keeps loaded attributes readable after commit.
# With async sessions an expired attribute would trigger a lazy load, which fails.
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, closed when the request ends."""
    async with SessionLocal() as session:
        yield session
