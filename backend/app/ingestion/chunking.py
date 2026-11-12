from dataclasses import dataclass

from app.parsing.base import Block


@dataclass(frozen=True)
class ChunkData:
    index: int
    text: str
    page_start: int | None
    page_end: int | None
    section_path: str | None


# One piece of text with its page. The unit of packing: a line of a PDF or a paragraph.
_Unit = tuple[str, int | None]


def chunk_blocks(
    blocks: list[Block], max_chars: int = 1500, overlap_chars: int = 200
) -> list[ChunkData]:
    """Split parsed blocks into chunks for embedding. A pure function: no I/O, easy to test.

    Rules:
    - A heading always starts a new chunk, so one chunk never mixes two clauses.
    - Inside a section, lines are packed into a chunk until it reaches `max_chars`.
    - The next chunk of the same section starts with the last ~`overlap_chars` of the
      previous one, so a sentence cut at the boundary still appears whole somewhere.
    - Each chunk text starts with its section heading (when there is one): the heading
      carries meaning ("Termination") that the body alone may not.

    Sizes are in characters, not tokens, so chunking does not depend on any tokenizer.
    1500 characters is roughly 350-450 tokens, far below the model's context limit.
    """
    if max_chars <= 0 or overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("need 0 <= overlap_chars < max_chars")

    chunks: list[ChunkData] = []
    section: str | None = None
    units: list[_Unit] = []

    def flush() -> None:
        chunks.extend(_pack(units, section, len(chunks), max_chars, overlap_chars))
        units.clear()

    for block in blocks:
        text = block.text.strip()
        if not text:
            continue
        if block.is_heading:
            flush()
            section = text[:500]  # the column is String(500)
        else:
            units.extend((piece, block.page) for piece in _split_long(text, max_chars))
    flush()
    return chunks


def _split_long(text: str, max_chars: int) -> list[str]:
    """Cut a single oversized paragraph at spaces, so no unit exceeds max_chars."""
    pieces: list[str] = []
    rest = text
    while len(rest) > max_chars:
        cut = rest.rfind(" ", 0, max_chars)
        if cut <= 0:
            cut = max_chars  # a "word" longer than max_chars (e.g. base64): hard cut
        pieces.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    pieces.append(rest)
    return pieces


def _pack(
    units: list[_Unit],
    section: str | None,
    first_index: int,
    max_chars: int,
    overlap_chars: int,
) -> list[ChunkData]:
    result: list[ChunkData] = []
    current: list[_Unit] = []
    size = 0

    def emit() -> None:
        body = "\n".join(text for text, _ in current)
        pages = [page for _, page in current if page is not None]
        result.append(
            ChunkData(
                index=first_index + len(result),
                text=f"{section}\n{body}" if section else body,
                page_start=min(pages) if pages else None,
                page_end=max(pages) if pages else None,
                section_path=section,
            )
        )

    for unit in units:
        added = len(unit[0]) + 1  # +1 for the newline that joins units
        if current and size + added > max_chars:
            emit()
            # Keep the tail of the finished chunk as overlap: the newest units whose
            # total size fits in overlap_chars. Walking backwards keeps the order.
            tail: list[_Unit] = []
            tail_size = 0
            for previous in reversed(current):
                if tail_size + len(previous[0]) + 1 > overlap_chars:
                    break
                tail.insert(0, previous)
                tail_size += len(previous[0]) + 1
            current, size = tail, tail_size
            # The overlap must not push the new chunk over the limit.
            while current and size + added > max_chars:
                dropped = current.pop(0)
                size -= len(dropped[0]) + 1
        current.append(unit)
        size += added
    if current:
        emit()
    return result
