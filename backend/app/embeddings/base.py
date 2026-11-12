from typing import Protocol


class EmbedderUnavailableError(Exception):
    """The embedding service cannot be used right now (down, model not pulled, overloaded).

    This is a problem with the infrastructure, not with the document, so the worker
    keeps the document waiting and tries again later instead of marking it as failed.
    """


class EmbeddingError(Exception):
    """The embedding service rejected this specific input. Retrying will not help."""


class Embedder(Protocol):
    """Turns text into vectors. The rest of the app depends only on this interface."""

    # Stored with every chunk, so vectors from different models are never mixed up.
    model_name: str

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...
