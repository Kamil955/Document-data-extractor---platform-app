import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.base import Embedder
from app.llm.base import LLM, LLMError
from app.models import FieldType
from app.retrieval.ask import Citation, answer_question
from app.retrieval.search import SearchHit

# One sentence per field type, appended to the question. It shapes the answer so the template can
# use it, and tells the model what to do when the document is silent.
_NOT_FOUND = "If the excerpts do not address it, say it was not found."
_TYPE_HINTS: dict[FieldType, str] = {
    FieldType.TEXT: "Answer concisely, keeping numbers, dates and names exactly as written. "
    f"{_NOT_FOUND}",
    FieldType.NUMBER: "Answer with a number and its unit if the document states one "
    f"(for example '10 business days'). {_NOT_FOUND}",
    FieldType.DATE: f"Answer with a date, as written in the document. {_NOT_FOUND}",
    # Inference is the danger here: "no exclusivity" is not "no non-compete". Silence in the
    # document must stay "not found", so "No" needs an explicit statement.
    FieldType.BOOLEAN: "Answer 'Yes' only if the document explicitly contains such a "
    "provision, and 'No' only if it explicitly states the opposite. If the document does not "
    "address it, say it was not found.",
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
    retrieved: list[SearchHit]
    # Set when the model gave an unusable reply for this field (the other fields still run).
    error: str | None = None


def search_query_for(field: FieldSpec) -> str:
    """Short text that describes the field: this is what is matched against the chunks."""
    return f"{field.label}. {field.description}" if field.description else field.label


def instruction_for(field: FieldSpec) -> str:
    """The question the model gets for one field.

    A plain question ("What does the document say about X?"), not "what is the VALUE of
    the field X": measured on real contracts the second wording made the model refuse
    descriptive fields (insurance, payment terms) although the right clause was in front of it.
    """
    about = f"'{field.label}'" + (f" ({field.description})" if field.description else "")
    return f"What does the document say about {about}? {_TYPE_HINTS[field.field_type]}"


def _is_verified(field: FieldSpec, value: str, supported: bool) -> bool:
    """A quote can prove that something IS in the document, never that it is NOT.

    "No" for a yes/no field is a claim about absence, so even a verbatim quote (usually from a
    neighbouring clause, like "No Exclusivity" for a non-compete question) does not back it.
    It is reported as not verified, which sends it to a human check.
    """
    is_negative = field.field_type is FieldType.BOOLEAN and value.strip().lower().startswith("no")
    return supported and not is_negative


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
        return FieldResult(
            field.key, field.label, field.field_type, "", False, False, [], [], str(exc)
        )
    return FieldResult(
        field.key,
        field.label,
        field.field_type,
        answer.answer,
        answer.found,
        _is_verified(field, answer.answer, answer.supported),
        answer.citations,
        answer.retrieved,
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
