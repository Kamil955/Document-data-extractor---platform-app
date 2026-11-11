from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError

from app.core.db import get_session
from app.main import app


def make_client() -> AsyncClient:
    # In-process client: calls the ASGI app directly, no server or network involved.
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_liveness_needs_no_database() -> None:
    async with make_client() as http:
        response = await http.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.integration
async def test_readiness_with_database(client: AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_readiness_returns_503_when_database_is_down() -> None:
    class BrokenSession:
        async def execute(self, *_args: object, **_kwargs: object) -> None:
            raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    async def broken_session() -> AsyncIterator[BrokenSession]:
        yield BrokenSession()

    app.dependency_overrides[get_session] = broken_session
    try:
        async with make_client() as http:
            response = await http.get("/health/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
