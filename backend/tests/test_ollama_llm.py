import json

import httpx
import pytest

from app.llm.base import LLMError, LLMUnavailableError
from app.llm.ollama import OllamaLLM

SCHEMA = {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]}


def make_llm(handler) -> OllamaLLM:
    client = httpx.AsyncClient(base_url="http://ollama", transport=httpx.MockTransport(handler))
    return OllamaLLM("http://ollama", "test-llm", num_ctx=4096, client=client)


def reply(content: str, done_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200, json={"message": {"role": "assistant", "content": content}, "done_reason": done_reason}
    )


async def test_request_shape_and_parsed_result() -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return reply('{"x": "value"}')

    result = await make_llm(handler).generate_json("be brief", "question?", SCHEMA)

    assert result == {"x": "value"}
    body = seen[0]
    assert body["model"] == "test-llm"
    assert body["stream"] is False
    assert body["think"] is False  # no reasoning tokens for extraction
    assert body["format"] == SCHEMA  # the schema constrains the generation
    assert body["options"] == {"temperature": 0, "num_ctx": 4096}
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


async def test_connection_error_means_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(LLMUnavailableError):
        await make_llm(handler).generate_json("s", "u", SCHEMA)


async def test_missing_model_means_unavailable_and_names_the_fix() -> None:
    with pytest.raises(LLMUnavailableError, match="ollama pull test-llm"):
        await make_llm(lambda r: httpx.Response(404)).generate_json("s", "u", SCHEMA)


async def test_server_error_means_unavailable() -> None:
    with pytest.raises(LLMUnavailableError):
        await make_llm(lambda r: httpx.Response(503)).generate_json("s", "u", SCHEMA)


async def test_rejected_request_is_a_permanent_error() -> None:
    with pytest.raises(LLMError):
        await make_llm(lambda r: httpx.Response(400, json={"error": "bad"})).generate_json(
            "s", "u", SCHEMA
        )


@pytest.mark.parametrize("content", ["not json at all", "[1, 2]", ""])
async def test_unusable_content_is_an_error(content: str) -> None:
    with pytest.raises(LLMError):
        await make_llm(lambda r: reply(content)).generate_json("s", "u", SCHEMA)


async def test_cut_off_answer_is_an_error() -> None:
    with pytest.raises(LLMError, match="cut off"):
        await make_llm(lambda r: reply('{"x": "par', done_reason="length")).generate_json(
            "s", "u", SCHEMA
        )
