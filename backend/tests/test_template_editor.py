import io

import pytest
from docx import Document
from httpx import AsyncClient

from app.core.content_types import DOCX_MIME
from app.filling.docx import find_placeholders
from app.filling.template_docx import MAX_EDIT_BLOCKS, build_docx, read_content
from app.llm.base import LLMError
from app.llm.rewrite import rewrite_passage
from app.schemas import PreviewParagraph, PreviewSegment, PreviewTable
from tests.fakes import FakeLLM, InMemoryStorage
from tests.test_template_documents import summary_docx, upload, word_file

pytestmark = pytest.mark.integration


def para(text: str, style: str = "normal", level: int = 1, **marks) -> dict:
    return {
        "type": "paragraph",
        "style": style,
        "level": level,
        "segments": [{"text": text, "key": None, **marks}] if text else [],
    }


def reopen(data: bytes) -> Document:
    return Document(io.BytesIO(data))


async def template_with_document(client: AsyncClient) -> str:
    response = await upload(client, summary_docx())
    return response.json()["id"]


def test_the_editor_model_survives_a_round_trip() -> None:
    def build(document) -> None:
        document.add_heading("Title {{term}}", level=2)
        document.add_paragraph("Plain ")
        document.add_paragraph("item", style="List Bullet")
        table = document.add_table(rows=2, cols=2)
        table.rows[1].cells[1].text = "{{governing_law}}"

    original = read_content(word_file(build))
    saved = build_docx(original.blocks, None)
    again = read_content(saved)

    assert again.blocks == original.blocks
    assert find_placeholders(saved) == ["term", "governing_law"]


def test_saving_keeps_the_headers_and_footers_of_the_file() -> None:
    def build(document) -> None:
        document.add_paragraph("Body")
        document.sections[0].footer.paragraphs[0].text = "Law: {{governing_law}}"

    base = word_file(build)
    saved = build_docx([PreviewParagraph(segments=[PreviewSegment(text="New body")])], base)

    document = reopen(saved)
    assert [p.text for p in document.paragraphs] == ["New body"]
    assert document.sections[0].footer.paragraphs[0].text == "Law: {{governing_law}}"


def test_formatting_levels_and_adjacent_tables_are_written() -> None:
    blocks = [
        PreviewParagraph(
            style="heading", level=3, segments=[PreviewSegment(text="H", bold=True, underline=True)]
        ),
        PreviewParagraph(style="title", segments=[PreviewSegment(text="T")]),
        PreviewTable(rows=[[[PreviewParagraph(segments=[PreviewSegment(text="a")])]]]),
        PreviewTable(rows=[[[PreviewParagraph(segments=[PreviewSegment(text="b", italic=True)])]]]),
    ]
    document = reopen(build_docx(blocks, None))

    assert document.paragraphs[0].style.name == "Heading 3"
    assert document.paragraphs[0].runs[0].underline is True
    assert document.paragraphs[1].style.name == "Title"
    assert len(document.tables) == 2  # kept apart by the empty paragraph between them
    assert document.tables[1].rows[0].cells[0].paragraphs[0].runs[0].italic is True


def test_a_file_without_list_and_table_styles_still_saves_readably() -> None:
    document = Document()
    for name in ("List Bullet", "Table Grid"):
        element = document.styles[name].element
        element.getparent().remove(element)
    buffer = io.BytesIO()
    document.save(buffer)

    blocks = [
        PreviewParagraph(style="list", segments=[PreviewSegment(text="item")]),
        PreviewTable(rows=[[[PreviewParagraph(segments=[PreviewSegment(text="x")])]]]),
    ]
    saved = reopen(build_docx(blocks, buffer.getvalue()))

    assert saved.paragraphs[0].text == "• item"
    assert (
        saved.tables[0]._tbl.tblPr.find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblBorders"
        )
        is not None
    )


def test_control_characters_do_not_break_saving() -> None:
    saved = build_docx([PreviewParagraph(segments=[PreviewSegment(text="a\x00b\x0cc")])], None)

    assert reopen(saved).paragraphs[0].text == "abc"


def test_the_editor_warns_about_what_it_cannot_keep() -> None:
    def build(document) -> None:
        outer = document.add_table(rows=1, cols=2)
        outer.cell(0, 0).merge(outer.cell(0, 1))
        outer.cell(0, 0).add_table(1, 1)

    notes = read_content(word_file(build)).notes

    assert "Tables inside table cells are flattened into plain paragraphs." in notes
    assert "Merged table cells become separate cells." in notes


def test_a_document_that_is_too_long_is_refused_not_cut() -> None:
    def build(document) -> None:
        for _ in range(MAX_EDIT_BLOCKS + 1):
            document.add_paragraph("x")

    from app.filling.docx import DocxFillError

    with pytest.raises(DocxFillError, match="too long"):
        read_content(word_file(build))


async def test_content_is_read_and_saved_through_the_api(
    client: AsyncClient, storage: InMemoryStorage
) -> None:
    template_id = await template_with_document(client)

    content = (await client.get(f"/templates/{template_id}/content")).json()
    assert content["blocks"][0]["style"] == "heading"
    assert content["notes"] == []

    edited = [para("Rewritten {{term}}", "heading"), para("Only this {{governing_law}}")]
    saved = await client.put(f"/templates/{template_id}/content", json={"blocks": edited})

    assert saved.status_code == 200
    preview = (await client.get(f"/templates/{template_id}/preview")).json()
    assert [p["key"] for p in preview["placeholders"]] == ["term", "governing_law"]
    assert [p["known"] for p in preview["placeholders"]] == [True, True]
    assert preview["unused_fields"] == ["notice_days", "mystery"]
    assert len(storage.blobs) == 1  # replaced in place, not duplicated


async def test_content_of_a_template_without_a_document_is_404_and_can_be_created(
    client: AsyncClient,
) -> None:
    created = await client.post(
        "/templates",
        json={
            "name": "Blank",
            "description": None,
            "fields": [{"key": "term", "label": "Term", "description": None, "type": "text"}],
        },
    )
    template_id = created.json()["id"]

    assert (await client.get(f"/templates/{template_id}/content")).status_code == 404

    saved = await client.put(
        f"/templates/{template_id}/content", json={"blocks": [para("Term: {{term}}")]}
    )
    assert saved.status_code == 200
    assert saved.json()["docx_filename"] == "Blank.docx"
    download = await client.get(f"/templates/{template_id}/docx")
    assert download.headers["content-type"] == DOCX_MIME
    assert find_placeholders(download.content) == ["term"]


async def test_saving_content_validates_the_shape(client: AsyncClient) -> None:
    template_id = await template_with_document(client)

    bad = await client.put(
        f"/templates/{template_id}/content", json={"blocks": [{"type": "paragraph", "style": "x"}]}
    )

    assert bad.status_code == 422


# --- rewriting a passage with the model -------------------------------------------------


async def test_rewrite_returns_the_model_text(client: AsyncClient, llm: FakeLLM) -> None:
    llm.response = {"text": "  The Parties agree. "}

    response = await client.post(
        "/templates/rewrite", json={"text": "We agree.", "instruction": "More formal"}
    )

    assert response.status_code == 200
    assert response.json() == {"text": "The Parties agree."}
    system, user, _ = llm.calls[0]
    assert "PASSAGE:\nWe agree." in user and "INSTRUCTION:\nMore formal" in user
    assert "SURROUNDING" not in user


async def test_rewrite_gives_the_model_the_context_when_there_is_one(
    client: AsyncClient, llm: FakeLLM
) -> None:
    llm.response = {"text": "ok"}

    await client.post(
        "/templates/rewrite",
        json={"text": "a", "instruction": "b", "context": "the whole paragraph"},
    )

    assert (
        "SURROUNDING TEXT (for tone only, do not rewrite it):\nthe whole paragraph"
        in (llm.calls[0][1])
    )


async def test_rewrite_retries_once_when_a_placeholder_is_lost() -> None:
    answers = iter([{"text": "Law applies."}, {"text": "The law of {{governing_law}} applies."}])
    llm = FakeLLM(lambda _prompt: next(answers))

    result = await rewrite_passage(llm, "Law: {{governing_law}}.", "formal")

    assert result == "The law of {{governing_law}} applies."
    assert "Your previous answer changed the placeholders" in llm.calls[1][1]
    assert "{{governing_law}}" in llm.calls[1][1]


async def test_rewrite_gives_up_when_placeholders_stay_wrong() -> None:
    llm = FakeLLM({"text": "Law applies, see {{other}}."})

    with pytest.raises(LLMError, match="placeholders"):
        await rewrite_passage(llm, "Law: {{governing_law}}.", "formal")
    assert len(llm.calls) == 2


async def test_rewrite_rejects_an_empty_answer() -> None:
    with pytest.raises(LLMError, match="empty"):
        await rewrite_passage(FakeLLM({"text": "  "}), "text", "shorter")


async def test_rewrite_reports_a_model_that_is_down(client: AsyncClient, llm: FakeLLM) -> None:
    from app.llm.base import LLMUnavailableError

    async def down(*_args):
        raise LLMUnavailableError("Ollama is not reachable")

    llm.generate_json = down  # type: ignore[method-assign]

    response = await client.post("/templates/rewrite", json={"text": "a", "instruction": "b"})

    assert response.status_code == 503
    assert "Ollama" in response.json()["detail"]


async def test_rewrite_validates_the_request(client: AsyncClient) -> None:
    response = await client.post("/templates/rewrite", json={"text": "", "instruction": "x"})

    assert response.status_code == 422


async def test_content_can_be_saved_again_and_again(
    client: AsyncClient, storage: InMemoryStorage
) -> None:
    # The storage refuses to replace a blob unless asked to (like Azure); a template's
    # document is replaced on purpose, every save.
    template_id = await template_with_document(client)

    for text in ("First {{term}}", "Second {{term}}", "Third {{term}}"):
        saved = await client.put(f"/templates/{template_id}/content", json={"blocks": [para(text)]})
        assert saved.status_code == 200

    preview = (await client.get(f"/templates/{template_id}/preview")).json()
    assert preview["blocks"][0]["segments"][0]["text"] == "Third "
    assert len(storage.blobs) == 1


async def test_a_template_document_can_be_replaced_by_upload_twice(
    client: AsyncClient,
) -> None:
    template_id = await template_with_document(client)

    for _ in range(2):
        replaced = await client.put(
            f"/templates/{template_id}/docx",
            files={"file": ("again.docx", summary_docx(), DOCX_MIME)},
        )
        assert replaced.status_code == 200
