import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.base import Embedder
from app.llm.base import LLM, LLMError
from app.models import FieldType
from app.retrieval.ask import Citation, answer_question

# One sentence per field type, appended to the instruction. The model decides nothing about
# the format by itself, so the value comes back in a shape the template can use.
_TYPE_HINTS: dict[FieldType, str] = {
    FieldType.TEXT: "Give the value exactly as written in the document.",
    FieldType.NUMBER: "Give a number, with its unit if the document states one (for example "
    "'10 business days').",
    FieldType.DATE: "Give a date, as written in the document.",
    FieldType.BOOLEAN: "Answer 'Yes' or 'No'.",
}


@dataclass(frozen=True)
class FieldSpec:
    """What to extract. Built from a stored template or sent inline in a request."""

    key: str
    label: str
    description: str | None = None
    field_type: FieldType = FieldType.TEXT


@dataclass(frozen=True)
class FieldResult:
    key: str
    label: str
    field_type: FieldType
    value: str
    found: bool
    # found AND at least one quote that was verified against the document text.
    supported: bool
    citations: list[Citation]
    # Set when the model gave an unusable reply for this field (the other fields still run).
    error: str | None = None


def search_query_for(field: FieldSpec) -> str:
    """Short text that describes the field: this is what is matched against the chunks."""
    return f"{field.label}. {field.description}" if field.description else field.label


def instruction_for(field: FieldSpec) -> str:
    """The question the model gets for one field."""
    about = f"'{field.label}'" + (f" ({field.description})" if field.description else "")
    return (
        f"What is the value of the field {about} in this document? "
        f"{_TYPE_HINTS[field.field_type]} "
        "If the excerpts do not state it, say it was not found."
    )


async def extract_field(
    session: AsyncSession,
    embedder: Embedder,
    llm: LLM,
    field: FieldSpec,
    *,
    document_id: uuid.UUID,
    limit: int = 5,
) -> FieldResult:
    try:
        answer = await answer_question(
            session,
            embedder,
            llm,
            instruction_for(field),
            limit=limit,
            document_id=document_id,
            search_query=search_query_for(field),
        )
    except LLMError as exc:
        # One bad reply must not throw away the other fields. Unavailable models are not
        # caught here: if Ollama is down every field would fail, so the request fails (503).
        return FieldResult(field.key, field.label, field.field_type, "", False, False, [], str(exc))
    return FieldResult(
        field.key,
        field.label,
        field.field_type,
        answer.answer,
        answer.found,
        answer.supported,
        answer.citations,
    )


async def extract_fields(
    session: AsyncSession,
    embedder: Embedder,
    llm: LLM,
    fields: list[FieldSpec],
    *,
    document_id: uuid.UUID,
    limit: int = 5,
) -> list[FieldResult]:
    # Sequential on purpose: one local model on one GPU serves one request at a time, so
    # running fields in parallel would only queue them inside Ollama.
    return [
        await extract_field(session, embedder, llm, field, document_id=document_id, limit=limit)
        for field in fields
    ]
