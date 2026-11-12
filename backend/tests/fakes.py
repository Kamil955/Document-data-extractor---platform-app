from app.storage.base import BlobNotFoundError


class InMemoryStorage:
    """A BlobStorage that keeps files in a dict. Fast, and needs no emulator."""

    def __init__(self) -> None:
        self.blobs: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        self.blobs[key] = (data, content_type)

    async def get(self, key: str) -> bytes:
        try:
            return self.blobs[key][0]
        except KeyError:
            raise BlobNotFoundError(key) from None

    async def delete(self, key: str) -> None:
        self.blobs.pop(key, None)


class FakeEmbedder:
    """Deterministic vectors without a model: the same text always gives the same vector.

    Vectors are seeded from a hash of the text, so different texts are almost orthogonal
    and a text is always the nearest neighbour of itself. That is enough to test the whole
    pipeline (storage, pgvector, ordering) without Ollama or a GPU.
    """

    model_name = "fake-embedder"

    def __init__(self, dim: int = 1024) -> None:
        self._dim = dim
        self.calls: list[list[str]] = []

    def _vector(self, text: str) -> list[float]:
        import hashlib
        import math
        import random

        rng = random.Random(hashlib.sha256(text.encode()).digest())
        raw = [rng.gauss(0, 1) for _ in range(self._dim)]
        norm = math.sqrt(sum(x * x for x in raw))
        return [x / norm for x in raw]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


class UnavailableEmbedder(FakeEmbedder):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        from app.embeddings.base import EmbedderUnavailableError

        raise EmbedderUnavailableError("Ollama is down (test)")
