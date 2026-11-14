import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.embeddings.base import Embedder
from app.llm.base import LLM
from app.retrieval.search import SearchHit, search_chunks

# Neutral wording on purpose: nothing here is specific to contracts, so the same prompt
# works for any document type. What to look for comes from the question (later: from the
# field definition of a template).
SYSTEM_PROMPT = """\
You answer questions about a document using ONLY the numbered excerpts given by the user.

Rules:
1. If the excerpts do not contain the answer, set "found" to false, leave "answer" empty \
and return no citations. Do not guess.
2. Otherwise answer concisely, in the language of the question, keeping values (numbers, \
dates, names, durations) exactly as written in the excerpts.
3. For every statement you rely on, add a citation: the excerpt number and a quote copied \
character for character from that excerpt (3 to 25 words, no ellipses).
4. Never use knowledge from outside the excerpts."""

ANSWER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "answer": {"type": "string"},
        "citations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"excerpt": {"type": "integer"}, "quote": {"type": "string"}},
                "required": ["excerpt", "quote"],
            },
        },
    },
    "required": ["found", "answer", "citations"],
}

# Typographic variants that PDFs use and models normalise away when they copy a quote.
_QUOTE_TRANSLATION = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def _normalize(text: str) -> str:
    return " ".join(text.translate(_QUOTE_TRANSLATION).split()).casefold()


@dataclass(frozen=True)
class Citation:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page_start: int | None
    page_end: int | None
    section_path: str | None
    quote: str
    # True only if the quote really occurs in the cited chunk. A model can invent a plausible
    # quote; this check is what makes a citation trustworthy.
    verified: bool


@dataclass(frozen=True)
class Answer:
    question: str
    found: bool
    answer: str
    # found AND at least one citation that was verified against the source text.
    supported: bool
    citations: list[Citation]
    retrieved: list[SearchHit]
    model: str


def build_user_prompt(question: str, hits: list[SearchHit]) -> str:
    parts = ["Excerpts:"]
    for number, hit in enumerate(hits, start=1):
        chunk = hit.chunk
        where = []
        if chunk.page_start is not None:
            where.append(f"page {chunk.page_start}")
        if chunk.section_path:
            where.append(f"section {chunk.section_path}")
        label = f" ({', '.join(where)})" if where else ""
        parts.append(f"[{number}]{label}\n{chunk.text}")
    parts.append(f"Question: {question}")
    return "\n\n".join(parts)


def _verify_citations(raw: Any, hits: list[SearchHit]) -> list[Citation]:
    citations: list[Citation] = []
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        number, quote = item.get("excerpt"), item.get("quote")
        # The model may cite an excerpt that does not exist: ignore such citations.
        if (
            not isinstance(number, int)
            or not 1 <= number <= len(hits)
            or not isinstance(quote, str)
        ):
            continue
        hit = hits[number - 1]
        chunk = hit.chunk
        quote = quote.strip()
        citations.append(
            Citation(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                filename=hit.filename,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                section_path=chunk.section_path,
                quote=quote,
                verified=bool(quote) and _normalize(quote) in _normalize(chunk.text),
            )
        )
    return citations


async def answer_question(
    session: AsyncSession,
    embedder: Embedder,
    llm: LLM,
    question: str,
    *,
    limit: int = 5,
    document_id: uuid.UUID | None = None,
) -> Answer:
    hits = await search_chunks(session, embedder, question, limit=limit, document_id=document_id)
    if not hits:
        # Nothing indexed to read: do not spend a model call (and do not invite a guess).
        return Answer(question, False, "", False, [], [], llm.model_name)

    raw = await llm.generate_json(SYSTEM_PROMPT, build_user_prompt(question, hits), ANSWER_SCHEMA)

    answer = str(raw.get("answer", "")).strip()
    found = bool(raw.get("found")) and bool(answer)
    citations = _verify_citations(raw.get("citations"), hits) if found else []
    supported = found and any(c.verified for c in citations)
    return Answer(
        question, found, answer if found else "", supported, citations, hits, llm.model_name
    )
