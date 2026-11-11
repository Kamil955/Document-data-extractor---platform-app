from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health
from app.core.db import engine


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    # Runs on shutdown: close pooled connections cleanly.
    await engine.dispose()


def create_app() -> FastAPI:
    # An app factory keeps construction in one place and makes it easy to build
    # a differently configured app in tests later.
    app = FastAPI(title="Contract Extractor", lifespan=lifespan)
    app.include_router(health.router)
    return app


app = create_app()
