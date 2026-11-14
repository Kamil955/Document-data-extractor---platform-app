import uuid

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration  # needs Postgres

NDA = {
    "name": "NDA summary",
    "description": "Key terms of a mutual NDA",
    "fields": [
        {"key": "term", "label": "Term of the agreement", "type": "text"},
        {
            "key": "notice_days",
            "label": "Termination notice",
            "description": "written notice needed to terminate",
            "type": "number",
        },
        {"key": "governing_law", "label": "Governing law"},
    ],
}


async def test_create_and_read_back_keeps_field_order_and_types(client: AsyncClient) -> None:
    created = await client.post("/templates", json=NDA)

    assert created.status_code == 201
    body = created.json()
    assert [f["key"] for f in body["fields"]] == ["term", "notice_days", "governing_law"]
    assert [f["type"] for f in body["fields"]] == ["text", "number", "text"]  # text is the default
    assert body["fields"][1]["description"] == "written notice needed to terminate"

    fetched = await client.get(f"/templates/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == body

    listed = await client.get("/templates")
    assert body["id"] in [t["id"] for t in listed.json()]


@pytest.mark.parametrize(
    "bad_field",
    [
        {"key": "Has Spaces", "label": "x"},
        {"key": "1starts_with_digit", "label": "x"},
        {"key": "ok", "label": ""},
        {"key": "ok", "label": "x", "type": "color"},
    ],
)
async def test_invalid_field_is_rejected(client: AsyncClient, bad_field: dict) -> None:
    response = await client.post("/templates", json={"name": "T", "fields": [bad_field]})

    assert response.status_code == 422


async def test_duplicate_keys_and_empty_field_list_are_rejected(client: AsyncClient) -> None:
    duplicate = {"name": "T", "fields": [{"key": "a", "label": "A"}, {"key": "a", "label": "B"}]}

    assert (await client.post("/templates", json=duplicate)).status_code == 422
    assert (await client.post("/templates", json={"name": "T", "fields": []})).status_code == 422


async def test_delete_template(client: AsyncClient) -> None:
    template_id = (await client.post("/templates", json=NDA)).json()["id"]

    assert (await client.delete(f"/templates/{template_id}")).status_code == 204
    assert (await client.get(f"/templates/{template_id}")).status_code == 404
    assert (await client.delete(f"/templates/{template_id}")).status_code == 404


async def test_unknown_template_is_404(client: AsyncClient) -> None:
    assert (await client.get(f"/templates/{uuid.uuid4()}")).status_code == 404
