import io

import pytest
from docx import Document
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.content_types import DOCX_MIME
from app.filling.template_docx import preview_docx, starter_docx
from tests.fakes import FakeEmbedder, FakeLLM, InMemoryStorage
from tests.files import make_docx
from tests.test_ask import add_document
from tests.test_extract import extract_now, reply_by_field
from tests.test_templates import NDA

pytestmark = pytest.mark.integration  # needs Postgres (the template tables)


def word_file(build) -> bytes:
    document = Document()
    build(document)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def summary_docx() -> bytes:
    def build(document) -> None:
        document.add_heading("Summary of {{term}}", level=1)
        document.add_paragraph("Law: {{governing_law}} and {{notice_days}}; also {{mystery}}.")

    return word_file(build)


async def upload(
    client: AsyncClient, data: bytes, filename: str = "summary.docx", **form
) -> object:
    return await client.post(
        "/templates/from-docx", files={"file": (filename, data, DOCX_MIME)}, data=form
    )


async def test_a_template_is_created_from_the_placeholders_of_a_document(
    client: AsyncClient, storage: InMemoryStorage
) -> None:
    response = await upload(client, summary_docx(), "NDA_summary_card.docx")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "NDA summary card"  # from the file name
    assert body["docx_filename"] == "NDA_summary_card.docx"
    # In order of first appearance, with a readable label made from the key.
    assert [(f["key"], f["label"], f["type"]) for f in body["fields"]] == [
        ("term", "Term", "text"),
        ("governing_law", "Governing law", "text"),
        ("notice_days", "Notice days", "text"),
        ("mystery", "Mystery", "text"),
    ]
    assert len(storage.blobs) == 1  # the file is kept with the template


async def test_the_name_can_be_given(client: AsyncClient) -> None:
    response = await upload(client, summary_docx(), "x.docx", name="  My card ")

    assert response.json()["name"] == "My card"


async def test_a_document_without_placeholders_or_not_a_docx_is_refused(
    client: AsyncClient, storage: InMemoryStorage
) -> None:
    no_placeholders = await upload(client, make_docx())
    not_word = await upload(client, b"%PDF-1.7 hello")

    assert no_placeholders.status_code == 422 and "placeholders" in no_placeholders.json()["detail"]
    assert not_word.status_code == 415
    assert storage.blobs == {}  # nothing was stored for the refused files


async def test_preview_marks_placeholders_and_keeps_the_structure(client: AsyncClient) -> None:
    # NDA has the fields term, notice_days and governing_law: "mystery" has no field.
    created = (await client.post("/templates", json=NDA)).json()
    await client.put(
        f"/templates/{created['id']}/docx", files={"file": ("s.docx", summary_docx(), DOCX_MIME)}
    )

    preview = (await client.get(f"/templates/{created['id']}/preview")).json()

    heading, paragraph = preview["blocks"]
    assert heading["style"] == "heading" and heading["level"] == 1
    assert [s["text"] for s in heading["segments"]] == ["Summary of ", "{{term}}"]
    assert [s["key"] for s in paragraph["segments"]] == [
        None,
        "governing_law",
        None,
        "notice_days",
        None,
        "mystery",
        None,
    ]
    assert preview["placeholders"] == [
        {"key": "term", "known": True},
        {"key": "governing_law", "known": True},
        {"key": "notice_days", "known": True},
        {"key": "mystery", "known": False},  # no field of this template: nothing will fill it
    ]
    assert preview["unused_fields"] == []
    assert preview["truncated"] is False


async def test_fields_that_the_document_never_uses_are_reported(client: AsyncClient) -> None:
    created = (await client.post("/templates", json=NDA)).json()
    only_term = word_file(lambda d: d.add_paragraph("Only {{term}} here"))
    await client.put(
        f"/templates/{created['id']}/docx", files={"file": ("s.docx", only_term, DOCX_MIME)}
    )

    preview = (await client.get(f"/templates/{created['id']}/preview")).json()

    assert sorted(preview["unused_fields"]) == ["governing_law", "notice_days"]


def test_preview_of_formatting_tables_lists_and_split_placeholders() -> None:
    def build(document) -> None:
        paragraph = document.add_paragraph()
        paragraph.add_run("Plain ")
        paragraph.add_run("bold").bold = True
        # Word often splits one placeholder over several runs.
        paragraph.add_run(" {{gov").italic = True
        paragraph.add_run("erning_law}}")
        document.add_paragraph("an item", style="List Bullet")
        table = document.add_table(rows=1, cols=2)
        table.rows[0].cells[0].merge(table.rows[0].cells[1]).text = "{{term}}"

    preview = preview_docx(word_file(build), ["term", "governing_law"])

    first, item, table = preview.blocks
    assert [(s.text, s.bold, s.key) for s in first.segments] == [
        ("Plain ", False, None),
        ("bold", True, None),
        (" ", False, None),
        ("{{governing_law}}", False, "governing_law"),  # one placeholder, though two runs
    ]
    assert item.style == "list"
    assert len(table.rows) == 1 and len(table.rows[0]) == 1  # the merged cell is listed once
    assert table.rows[0][0][0].segments[0].key == "term"


def test_preview_is_cut_short_for_a_huge_document() -> None:
    def build(document) -> None:
        for i in range(450):
            document.add_paragraph(f"line {i}")

    preview = preview_docx(word_file(build), [])

    assert len(preview.blocks) == 400 and preview.truncated is True


def test_a_text_that_looks_like_markup_stays_text() -> None:
    # The preview is data, not HTML: nothing here can ever be interpreted as a tag.
    preview = preview_docx(word_file(lambda d: d.add_paragraph("<script>alert(1)</script>")), [])

    assert preview.blocks[0].segments[0].text == "<script>alert(1)</script>"


async def test_a_starter_document_is_made_from_the_fields(
    client: AsyncClient, storage: InMemoryStorage
) -> None:
    created = (await client.post("/templates", json=NDA)).json()
    assert created["docx_filename"] is None
    assert (await client.get(f"/templates/{created['id']}/preview")).status_code == 404

    generated = await client.post(f"/templates/{created['id']}/docx/generate")

    assert (
        generated.status_code == 200 and generated.json()["docx_filename"] == f"{NDA['name']}.docx"
    )
    preview = (await client.get(f"/templates/{created['id']}/preview")).json()
    assert [p["key"] for p in preview["placeholders"]] == ["term", "notice_days", "governing_law"]
    assert all(p["known"] for p in preview["placeholders"]) and preview["unused_fields"] == []
    # The second call would silently destroy the person's edits: it is refused.
    assert (await client.post(f"/templates/{created['id']}/docx/generate")).status_code == 409


def test_the_starter_document_is_a_valid_docx_with_a_table() -> None:
    data = starter_docx("Card", "About it", [("a_b", "A b"), ("c", "C")])

    document = Document(io.BytesIO(data))
    assert [c.text for c in document.tables[0].rows[1].cells] == ["A b", "{{a_b}}"]
    assert document.paragraphs[0].text == "Card"


async def test_the_document_can_be_downloaded_and_replaced(client: AsyncClient) -> None:
    original = summary_docx()
    template_id = (await upload(client, original, "first.docx")).json()["id"]

    downloaded = await client.get(f"/templates/{template_id}/docx")
    assert downloaded.status_code == 200 and downloaded.content == original
    assert "first.docx" in downloaded.headers["content-disposition"]

    replaced = await client.put(
        f"/templates/{template_id}/docx",
        files={
            "file": ("second.docx", word_file(lambda d: d.add_paragraph("{{term}}")), DOCX_MIME)
        },
    )
    assert replaced.json()["docx_filename"] == "second.docx"
    bad = await client.put(
        f"/templates/{template_id}/docx", files={"file": ("x.docx", b"nope", DOCX_MIME)}
    )
    assert bad.status_code == 415
    assert (
        await client.put(
            "/templates/00000000-0000-0000-0000-000000000000/docx",
            files={"file": ("x.docx", summary_docx(), DOCX_MIME)},
        )
    ).status_code == 404


async def test_deleting_a_template_deletes_its_document(
    client: AsyncClient, storage: InMemoryStorage
) -> None:
    template_id = (await upload(client, summary_docx())).json()["id"]
    assert len(storage.blobs) == 1

    assert (await client.delete(f"/templates/{template_id}")).status_code == 204

    assert storage.blobs == {}


async def test_filling_uses_the_template_document_when_no_file_is_sent(
    client: AsyncClient,
    db_session: AsyncSession,
    embedder: FakeEmbedder,
    llm: FakeLLM,
) -> None:
    document = await add_document(db_session, embedder)
    created = (await client.post("/templates", json=NDA)).json()
    await client.put(
        f"/templates/{created['id']}/docx",
        files={
            "file": (
                "law card.docx",
                word_file(lambda d: d.add_paragraph("Law: {{governing_law}}")),
                DOCX_MIME,
            )
        },
    )
    llm.response = reply_by_field
    extraction = await extract_now(
        client, db_session, embedder, llm, document.id, {"template_id": created["id"]}
    )

    response = await client.post(f"/extractions/{extraction['extraction_id']}/fill")

    assert response.status_code == 200
    assert Document(io.BytesIO(response.content)).paragraphs[0].text == "Law: State of Washington"
    assert "filled-law%20card.docx" in response.headers["content-disposition"]
    # A file sent with the request wins over the stored one.
    other = word_file(lambda d: d.add_paragraph("Other: {{governing_law}}"))
    sent = await client.post(
        f"/extractions/{extraction['extraction_id']}/fill",
        files={"file": ("o.docx", other, DOCX_MIME)},
    )
    assert Document(io.BytesIO(sent.content)).paragraphs[0].text == "Other: State of Washington"


async def test_filling_without_a_file_needs_a_template_with_a_document(
    client: AsyncClient,
    db_session: AsyncSession,
    embedder: FakeEmbedder,
    llm: FakeLLM,
) -> None:
    document_id = (await add_document(db_session, embedder)).id  # read before a rollback expires it
    created = (await client.post("/templates", json=NDA)).json()  # no document attached
    extraction = await extract_now(
        client, db_session, embedder, llm, document_id, {"template_id": created["id"]}
    )
    inline = await extract_now(
        client, db_session, embedder, llm, document_id, {"fields": [{"key": "a", "label": "A"}]}
    )

    with_template = await client.post(f"/extractions/{extraction['extraction_id']}/fill")
    without_template = await client.post(f"/extractions/{inline['extraction_id']}/fill")

    assert with_template.status_code == 400 and "no document" in with_template.json()["detail"]
    assert without_template.status_code == 400
