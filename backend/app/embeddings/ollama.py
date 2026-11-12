import httpx

from app.embeddings.base import EmbedderUnavailableError, EmbeddingError

# Qwen3-Embedding is "instruction aware": a search query is prefixed with a task
# description, documents are embedded as plain text. Skipping the prefix on queries
# lowers retrieval quality noticeably. (Format taken from the model card; verify it
# against your own retrieval tests before relying on it.)
QUERY_TASK = "Given a search query about a contract, retrieve relevant passages that answer it"


class OllamaEmbedder:
    def __init__(
        self,
        base_url: str,
        model: str,
        expected_dim: int,
        batch_size: int = 16,
        num_ctx: int = 2048,
        timeout_seconds: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model_name = model
        self._expected_dim = expected_dim
        self._batch_size = batch_size
        self._num_ctx = num_ctx
        # A client can be injected so tests can plug in a fake transport instead of a server.
        self._client = client or httpx.AsyncClient(
            base_url=base_url, timeout=httpx.Timeout(timeout_seconds, connect=5.0)
        )

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        # Batches keep a single request small. One request per chunk would be slow
        # (HTTP overhead), one request for a whole book could time out.
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(await self._embed(texts[start : start + self._batch_size]))
        return vectors

    async def embed_query(self, text: str) -> list[float]:
        prompt = f"Instruct: {QUERY_TASK}\nQuery:{text}"
        return (await self._embed([prompt]))[0]

    async def _embed(self, batch: list[str]) -> list[list[float]]:
        payload = {
            "model": self.model_name,
            "input": batch,
            # Ollama truncates over-long input silently by default, producing a vector
            # of the beginning of the text. We would rather get an error than a wrong vector.
            "truncate": False,
            # Context size: the model's maximum is 32k, which makes the server reserve
            # gigabytes of VRAM. Our chunks are ~500 tokens, so 2048 is plenty.
            "options": {"num_ctx": self._num_ctx},
        }
        try:
            response = await self._client.post("/api/embed", json=payload)
        except httpx.TransportError as exc:  # refused connection, timeout, DNS, ...
            raise EmbedderUnavailableError(f"Ollama is not reachable: {exc}") from exc

        if response.status_code == 404:
            raise EmbedderUnavailableError(
                f"model '{self.model_name}' not found in Ollama, run: ollama pull {self.model_name}"
            )
        if response.status_code >= 500:
            raise EmbedderUnavailableError(f"Ollama server error {response.status_code}")
        if response.status_code >= 400:
            raise EmbeddingError(
                f"Ollama rejected the input ({response.status_code}): {response.text[:300]}"
            )

        embeddings = response.json()["embeddings"]
        if len(embeddings) != len(batch):
            raise EmbeddingError(f"asked for {len(batch)} vectors, got {len(embeddings)}")
        for vector in embeddings:
            if len(vector) != self._expected_dim:
                # A different width means a different model than the schema was built for.
                # Better to stop here than to fail later in the database with a vague error.
                raise EmbeddingError(
                    f"model '{self.model_name}' returned {len(vector)} dimensions, "
                    f"the database expects {self._expected_dim}"
                )
        return embeddings

    async def close(self) -> None:
        await self._client.aclose()
