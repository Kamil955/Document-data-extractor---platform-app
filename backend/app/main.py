from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import documents, health
from app.core.config import get_settings
from app.core.db import engine
from app.storage.azure_blob import AzureBlobStorage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    storage = AzureBlobStorage(settings.azure_storage_connection_string, settings.blob_container)
    await storage.start()  # fails fast at startup if storage is unreachable
    app.state.storage = storage
    yield
    # Runs on shutdown: close the storage client and pooled database connections.
    await storage.close()
    await engine.dispose()


def create_app() -> FastAPI:
    # An app factory keeps construction in one place and makes it easy to build
    # a differently configured app in tests later.
    app = FastAPI(title="Contract Extractor", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(documents.router)
    return app


app = create_app()
