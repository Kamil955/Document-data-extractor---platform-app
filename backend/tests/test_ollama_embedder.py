import json

import httpx
import pytest

from app.embeddings.base import EmbedderUnavailableError, EmbeddingError
from app.embeddings.ollama import OllamaEmbedder

DIM = 4


def make_embedder(handler, batch_size: int = 2) -> OllamaEmbedder:
    # MockTransport answers requests in-process, so no Ollama server is needed.
    client = httpx.AsyncClient(base_url="http://ollama", transport=httpx.MockTransport(handler))
    return OllamaEmbedder("http://ollama", "test-model", DIM, batch_size=batch_size, client=client)


def ok_handler(requests: list[dict]):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        return httpx.Response(200, json={"embeddings": [[0.1] * DIM for _ in body["input"]]})

    return handler


async def test_request_shape_and_batching() -> None:
    sent: list[dict] = []
    embedder = make_embedder(ok_handler(sent), batch_size=2)

    vectors = await embedder.embed_documents(["a", "b", "c", "d", "e"])

    assert len(vectors) == 5
    assert [body["input"] for body in sent] == [["a", "b"], ["c", "d"], ["e"]]
    assert all(body["model"] == "test-model" for body in sent)
    # Silent truncation must be off, and the context window must be limited.
    assert all(body["truncate"] is False for body in sent)
    assert all(body["options"]["num_ctx"] == 2048 for body in sent)


async def test_query_gets_instruction_prefix_but_documents_do_not() -> None:
    sent: list[dict] = []
    embedder = make_embedder(ok_handler(sent))

    await embedder.embed_documents(["plain text"])
    await embedder.embed_query("what is the notice period?")

    assert sent[0]["input"] == ["plain text"]
    assert sent[1]["input"][0].startswith("Instruct: ")
    assert sent[1]["input"][0].endswith("Query:what is the notice period?")


async def test_connection_error_means_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(EmbedderUnavailableError):
        await make_embedder(handler).embed_documents(["x"])


async def test_missing_model_means_unavailable_and_names_the_fix() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(EmbedderUnavailableError, match="ollama pull test-model"):
        await make_embedder(handler).embed_documents(["x"])


async def test_server_error_means_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(EmbedderUnavailableError):
        await make_embedder(handler).embed_documents(["x"])


async def test_rejected_input_is_a_permanent_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "input length exceeds the context length"})

    with pytest.raises(EmbeddingError):
        await make_embedder(handler).embed_documents(["x"])


async def test_wrong_dimension_is_detected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[0.1] * (DIM + 1)]})

    with pytest.raises(EmbeddingError, match="dimensions"):
        await make_embedder(handler).embed_documents(["x"])
