"""Rewriting a passage of a template document with a language model."""

from app.filling.docx import PLACEHOLDER
from app.llm.base import LLM, LLMError

SYSTEM_PROMPT = """You are an editor of document templates (contracts, summaries, letters).
You get a PASSAGE and an INSTRUCTION. Rewrite the passage following the instruction.

Rules:
- Placeholders look like {{some_key}}. They are filled with data later. Keep every
  placeholder exactly as written, spelled the same, and do not add new ones.
- Change only what the instruction asks for. Keep the meaning, the facts and the language
  of the passage, unless the instruction says otherwise.
- Answer with the rewritten passage only: no comments, no quotation marks around it.
- Keep a similar length unless the instruction asks to shorten or expand."""

SCHEMA = {
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
    "additionalProperties": False,
}


def _keys(text: str) -> list[str]:
    return sorted(PLACEHOLDER.findall(text))


def _prompt(text: str, instruction: str, context: str | None) -> str:
    parts = []
    if context:
        parts.append(f"SURROUNDING TEXT (for tone only, do not rewrite it):\n{context}")
    parts.append(f"PASSAGE:\n{text}")
    parts.append(f"INSTRUCTION:\n{instruction}")
    return "\n\n".join(parts)


async def rewrite_passage(llm: LLM, text: str, instruction: str, context: str | None = None) -> str:
    """The passage rewritten as instructed, with its {{placeholders}} intact.

    A small model sometimes drops or renames a placeholder, and a template that loses one
    silently is worse than no rewrite. So the result is checked against the original and the
    model gets one more try with the mistake pointed out.
    """
    expected = _keys(text)
    prompt = _prompt(text, instruction, context)
    for attempt in range(2):
        result = await llm.generate_json(SYSTEM_PROMPT, prompt, SCHEMA)
        rewritten = result.get("text")
        if not isinstance(rewritten, str) or not rewritten.strip():
            raise LLMError("the model returned an empty answer")
        rewritten = rewritten.strip()
        if _keys(rewritten) == expected:
            return rewritten
        if attempt == 0:
            listed = ", ".join("{{" + key + "}}" for key in expected) or "none"
            prompt += (
                "\n\nYour previous answer changed the placeholders. "
                f"The passage must contain exactly these placeholders: {listed}. Try again."
            )
    raise LLMError(
        "the model did not keep the {{placeholders}} intact, try a different instruction"
    )
