"""Integration tests for the S2S-gated /v1/admin/catalog endpoints."""

import logging
from typing import Any

import pytest
from httpx import AsyncClient

from src.api.core.configs import settings as app_settings

TOKEN = "test-admin-token"
ADMIN = "/v1/admin/catalog"


@pytest.fixture
def admin_headers(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setattr(app_settings, "admin_service_token", TOKEN)
    return {
        "X-Service-Token": TOKEN,
        "X-Acting-Operator": "ops@crew.shop",
        "X-Acting-Role": "admin",
    }


async def _category_id(client: AsyncClient, name: str = "Single Origin") -> str:
    resp = await client.get("/v1/catalog/categories")
    return next(c["id"] for c in resp.json()["items"] if c["name"] == name)


def _coffee_payload(category_id: str) -> dict[str, Any]:
    return {
        "name": "Peru Decaf",
        "category_id": category_id,
        "product_type": "coffee",
        "price": "13.00",
        "coffee": {
            "region": "peru",
            "roast_level": "medium",
            "processing": "washed",
            "acidity": 3,
            "body": 3,
            "sweetness": 3,
            "altitude": 1500,
            "flavor_notes": {"keys": ["nutty"], "en": ["Nutty"], "ru": ["Орехи"]},
        },
    }


async def test_create_product(seeded_client: AsyncClient, admin_headers: dict[str, str]) -> None:
    payload = _coffee_payload(await _category_id(seeded_client))
    resp = await seeded_client.post(f"{ADMIN}/products", json=payload, headers=admin_headers)
    body = resp.json()
    assert resp.status_code == 201, resp.text
    assert body["name"] == "Peru Decaf"
    assert body["product_type"] == "coffee"
    assert body["coffee"]["region"] == "peru"
    assert body["rating"] is None and body["rating_count"] == 0

    # It now shows up in the public listing.
    listing = await seeded_client.get("/v1/catalog/products", params={"limit": 100})
    assert listing.json()["total"] == 13


async def test_create_rejected_without_token(seeded_client: AsyncClient) -> None:
    payload = _coffee_payload(await _category_id(seeded_client))
    resp = await seeded_client.post(f"{ADMIN}/products", json=payload)
    assert resp.status_code == 403
    assert resp.json()["error"]["error_code"] == "CATALOG_ADMIN_FORBIDDEN"


async def test_create_rejected_with_wrong_token(seeded_client: AsyncClient) -> None:
    payload = _coffee_payload(await _category_id(seeded_client))
    resp = await seeded_client.post(
        f"{ADMIN}/products",
        json=payload,
        headers={"X-Service-Token": "nope", "X-Acting-Operator": "ops@crew.shop"},
    )
    assert resp.status_code == 403


async def test_create_rejected_without_operator(
    seeded_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    payload = _coffee_payload(await _category_id(seeded_client))
    headers = {"X-Service-Token": admin_headers["X-Service-Token"]}
    resp = await seeded_client.post(f"{ADMIN}/products", json=payload, headers=headers)
    assert resp.status_code == 403


async def test_create_invalid_category_reference(
    seeded_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    payload = _coffee_payload("00000000-0000-0000-0000-000000000000")
    resp = await seeded_client.post(f"{ADMIN}/products", json=payload, headers=admin_headers)
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "CATALOG_INVALID_REFERENCE"


async def test_create_attribute_type_mismatch_rejected(
    seeded_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    payload = _coffee_payload(await _category_id(seeded_client))
    del payload["coffee"]
    payload["accessory"] = {"accessory_type": "tamper", "material": "steel"}
    resp = await seeded_client.post(f"{ADMIN}/products", json=payload, headers=admin_headers)
    assert resp.status_code == 422


async def test_update_product(seeded_client: AsyncClient, admin_headers: dict[str, str]) -> None:
    created = await seeded_client.post(
        f"{ADMIN}/products",
        json=_coffee_payload(await _category_id(seeded_client)),
        headers=admin_headers,
    )
    product_id = created.json()["id"]

    update = _coffee_payload(await _category_id(seeded_client))
    update["name"] = "Peru Decaf v2"
    update["price"] = "14.25"
    update.pop("product_type")  # type is immutable on update
    resp = await seeded_client.put(
        f"{ADMIN}/products/{product_id}", json=update, headers=admin_headers
    )
    body = resp.json()
    assert resp.status_code == 200
    assert body["name"] == "Peru Decaf v2"
    assert body["price"] == "14.25"


async def test_delete_product(seeded_client: AsyncClient, admin_headers: dict[str, str]) -> None:
    created = await seeded_client.post(
        f"{ADMIN}/products",
        json=_coffee_payload(await _category_id(seeded_client)),
        headers=admin_headers,
    )
    product_id = created.json()["id"]

    resp = await seeded_client.delete(f"{ADMIN}/products/{product_id}", headers=admin_headers)
    assert resp.status_code == 204

    detail = await seeded_client.get(f"/v1/catalog/products/{product_id}")
    assert detail.status_code == 404


async def test_category_crud(seeded_client: AsyncClient, admin_headers: dict[str, str]) -> None:
    created = await seeded_client.post(
        f"{ADMIN}/categories",
        json={"name": "Cold Brew", "description": "Ready-to-drink"},
        headers=admin_headers,
    )
    assert created.status_code == 201
    category_id = created.json()["id"]

    updated = await seeded_client.put(
        f"{ADMIN}/categories/{category_id}",
        json={"name": "Cold Brew & RTD"},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Cold Brew & RTD"

    deleted = await seeded_client.delete(f"{ADMIN}/categories/{category_id}", headers=admin_headers)
    assert deleted.status_code == 204


async def test_delete_non_empty_category_conflict(
    seeded_client: AsyncClient, admin_headers: dict[str, str]
) -> None:
    category_id = await _category_id(seeded_client)  # Single Origin has seeded coffees
    resp = await seeded_client.delete(f"{ADMIN}/categories/{category_id}", headers=admin_headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["error_code"] == "CATALOG_CATEGORY_NOT_EMPTY"


async def test_public_read_unaffected_without_credentials(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get("/v1/catalog/products", params={"limit": 5})
    assert resp.status_code == 200


async def test_write_is_audited(
    seeded_client: AsyncClient,
    admin_headers: dict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    payload = _coffee_payload(await _category_id(seeded_client))
    with caplog.at_level(logging.INFO, logger="src.catalog.admin.audit"):
        await seeded_client.post(f"{ADMIN}/products", json=payload, headers=admin_headers)
    record = next(r for r in caplog.records if getattr(r, "audit", False))
    assert record.operator == "ops@crew.shop"
    assert record.action == "create"
