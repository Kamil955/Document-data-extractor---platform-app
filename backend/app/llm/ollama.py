import json
from typing import Any

import httpx

from app.llm.base import LLMError, LLMUnavailableError


class OllamaLLM:
    def __init__(
        self,
        base_url: str,
        model: str,
        num_ctx: int = 8192,
        timeout_seconds: float = 300.0,
        keep_alive: str = "10m",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model_name = model
        self._num_ctx = num_ctx
        # How long Ollama keeps the model in VRAM after the last request. The first request
        # after that pays the loading time (tens of seconds), so a few minutes is worth it.
        self._keep_alive = keep_alive
        # Generating can take a while on a small GPU: a generous read timeout, but a short
        # connect timeout so that "Ollama is not running" fails fast.
        self._client = client or httpx.AsyncClient(
            base_url=base_url, timeout=httpx.Timeout(timeout_seconds, connect=5.0)
        )

    async def generate_json(self, system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.model_name,
            "stream": False,
            # Reasoning models spend hundreds of tokens "thinking" before they answer. For
            # extraction that is slower and fills the context window for no benefit.
            "think": False,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # A JSON schema here makes Ollama constrain the generation itself (grammar-based
            # decoding): the output is always valid JSON of this shape, even from a small
            # model. The CONTENT can still be wrong, which is why callers verify it.
            "format": schema,
            # temperature 0: the most likely answer every time, so results are repeatable.
            "options": {"temperature": 0, "num_ctx": self._num_ctx},
            "keep_alive": self._keep_alive,
        }
        try:
            response = await self._client.post("/api/chat", json=payload)
        except httpx.TransportError as exc:  # refused connection, timeout, DNS, ...
            raise LLMUnavailableError(f"Ollama is not reachable: {exc}") from exc

        if response.status_code == 404:
            raise LLMUnavailableError(
                f"model '{self.model_name}' not found in Ollama, run: ollama pull {self.model_name}"
            )
        if response.status_code >= 500:
            raise LLMUnavailableError(f"Ollama server error {response.status_code}")
        if response.status_code >= 400:
            raise LLMError(
                f"Ollama rejected the request ({response.status_code}): {response.text[:300]}"
            )

        body = response.json()
        if body.get("done_reason") == "length":
            # The model hit the token limit mid-answer, so the JSON is incomplete.
            raise LLMError("the answer was cut off (token limit reached)")
        try:
            result = json.loads(body["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise LLMError(f"the model did not return valid JSON: {exc}") from exc
        if not isinstance(result, dict):
            raise LLMError("the model returned JSON that is not an object")
        return result

    async def close(self) -> None:
        await self._client.aclose()
