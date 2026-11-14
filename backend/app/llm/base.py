from typing import Any, Protocol


class LLMUnavailableError(Exception):
    """The language model cannot be used right now (server down, model not pulled)."""


class LLMError(Exception):
    """The model answered, but not in a usable way (not JSON, cut off, request rejected)."""


class LLM(Protocol):
    """A text generator that answers with JSON matching a schema.

    The rest of the app depends only on this interface, so the model (or the provider:
    Ollama today, something else tomorrow) can be changed without touching the callers.
    """

    model_name: str

    async def generate_json(
        self, system: str, user: str, schema: dict[str, Any]
    ) -> dict[str, Any]: ...
