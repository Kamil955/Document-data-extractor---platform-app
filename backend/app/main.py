from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import ask, documents, extract, extractions, health, search, templates
from app.core.config import get_settings
from app.core.db import engine
from app.embeddings.ollama import OllamaEmbedder
from app.llm.ollama import OllamaLLM
from app.models import EMBEDDING_DIM
from app.storage.azure_blob import AzureBlobStorage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    storage = AzureBlobStorage(settings.azure_storage_connection_string, settings.blob_container)
    await storage.start()  # fails fast at startup if storage is unreachable
    app.state.storage = storage
    # Creating the client does not connect: the API starts even when Ollama is down and
    # /search answers 503 until it is back.
    embedder = OllamaEmbedder(
        settings.ollama_base_url,
        settings.embedding_model,
        EMBEDDING_DIM,
        query_instruction=settings.embedding_query_instruction,
    )
    app.state.embedder = embedder
    llm = OllamaLLM(
        settings.ollama_base_url,
        settings.llm_model,
        num_ctx=settings.llm_num_ctx,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    app.state.llm = llm
    yield
    # Runs on shutdown: close the storage client and pooled database connections.
    await llm.close()
    await embedder.close()
    await storage.close()
    await engine.dispose()


def create_app() -> FastAPI:
    # An app factory keeps construction in one place and makes it easy to build
    # a differently configured app in tests later.
    app = FastAPI(title="Contract Extractor", lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(documents.router)
    app.include_router(search.router)
    app.include_router(ask.router)
    app.include_router(templates.router)
    app.include_router(extract.router)
    app.include_router(extractions.router)
    return app


app = create_app()
