import pytest

from app.ingestion.chunking import chunk_blocks
from app.parsing.base import Block


def lines(count: int, page: int | None = 1, width: int = 40) -> list[Block]:
    return [Block(f"line {i:03d} ".ljust(width, "x"), page) for i in range(count)]


def test_small_document_is_one_chunk() -> None:
    chunks = chunk_blocks([Block("Hello world.", 1)])
    assert len(chunks) == 1
    assert chunks[0].text == "Hello world."
    assert (chunks[0].page_start, chunks[0].page_end) == (1, 1)
    assert chunks[0].section_path is None


def test_empty_and_blank_input_gives_no_chunks() -> None:
    assert chunk_blocks([]) == []
    assert chunk_blocks([Block("   ", 1)]) == []


def test_heading_starts_a_new_chunk_and_is_prefixed() -> None:
    blocks = [
        Block("1. Definitions", 1, True),
        Block("Supplier means ACME.", 1),
        Block("2. Payment", 2, True),
        Block("Pay within 30 days.", 2),
    ]
    chunks = chunk_blocks(blocks)
    assert [c.section_path for c in chunks] == ["1. Definitions", "2. Payment"]
    assert chunks[0].text == "1. Definitions\nSupplier means ACME."
    assert chunks[1].text == "2. Payment\nPay within 30 days."
    assert [c.index for c in chunks] == [0, 1]


def test_heading_without_body_produces_no_chunk() -> None:
    blocks = [Block("1. Empty", 1, True), Block("2. Real", 1, True), Block("Body.", 1)]
    chunks = chunk_blocks(blocks)
    assert [c.section_path for c in chunks] == ["2. Real"]


def test_chunks_respect_max_size() -> None:
    chunks = chunk_blocks(lines(100), max_chars=300, overlap_chars=60)
    assert len(chunks) > 5
    assert all(len(c.text) <= 300 for c in chunks)


def test_consecutive_chunks_overlap() -> None:
    chunks = chunk_blocks(lines(40), max_chars=300, overlap_chars=100)
    for previous, following in zip(chunks, chunks[1:], strict=False):
        last_line_of_previous = previous.text.splitlines()[-1]
        assert last_line_of_previous in following.text.splitlines()


def test_no_content_is_lost() -> None:
    blocks = lines(60)
    chunks = chunk_blocks(blocks, max_chars=300, overlap_chars=80)
    joined = "\n".join(c.text for c in chunks)
    assert all(block.text in joined for block in blocks)


def test_page_range_spans_pages() -> None:
    blocks = [Block("a" * 100, 1), Block("b" * 100, 2), Block("c" * 100, 3)]
    chunks = chunk_blocks(blocks, max_chars=1000)
    assert (chunks[0].page_start, chunks[0].page_end) == (1, 3)


def test_pages_are_none_for_docx_like_input() -> None:
    chunks = chunk_blocks([Block("text", None)])
    assert (chunks[0].page_start, chunks[0].page_end) == (None, None)


def test_overlong_paragraph_is_split_at_spaces() -> None:
    paragraph = " ".join(["word"] * 400)  # 1999 characters, one paragraph
    chunks = chunk_blocks([Block(paragraph, 1)], max_chars=500, overlap_chars=50)
    assert len(chunks) >= 4
    assert all(len(c.text) <= 500 for c in chunks)
    assert all(not c.text.startswith(("ord", "ord ")) for c in chunks)  # no word cut in half


def test_word_longer_than_limit_is_hard_cut() -> None:
    chunks = chunk_blocks([Block("x" * 1000, 1)], max_chars=300, overlap_chars=0)
    assert all(len(c.text) <= 300 for c in chunks)
    assert "".join(c.text for c in chunks) == "x" * 1000


def test_invalid_overlap_is_rejected() -> None:
    with pytest.raises(ValueError):
        chunk_blocks([Block("x", 1)], max_chars=100, overlap_chars=100)
