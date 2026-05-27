"""Integration tests for the public /v1/catalog endpoints against the seeded dataset."""

from typing import Any

from httpx import AsyncClient

PRODUCTS = "/v1/catalog/products"


async def _items(client: AsyncClient, **params: Any) -> list[dict[str, Any]]:
    resp = await client.get(PRODUCTS, params={"limit": 100, **params})
    assert resp.status_code == 200, resp.text
    return resp.json()["items"]


def _names(items: list[dict[str, Any]]) -> set[str]:
    return {item["name"] for item in items}


async def test_list_returns_all_active_products(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(PRODUCTS, params={"limit": 100})
    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 12
    assert len(body["items"]) == 12


async def test_list_pagination(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(PRODUCTS, params={"limit": 5, "offset": 0})
    body = resp.json()
    assert body["total"] == 12
    assert len(body["items"]) == 5
    assert body["limit"] == 5 and body["offset"] == 0


async def test_list_includes_rating_aggregate(seeded_client: AsyncClient) -> None:
    items = {item["name"]: item for item in await _items(seeded_client)}
    rated = items["Ethiopia Yirgacheffe"]
    assert rated["rating"] == 4.5
    assert rated["rating_count"] == 2
    # Unrated product reports null rating, zero count.
    unrated = items["Milk Pitcher 600ml"]
    assert unrated["rating"] is None
    assert unrated["rating_count"] == 0


async def test_list_product_carries_typed_attributes(seeded_client: AsyncClient) -> None:
    items = {item["name"]: item for item in await _items(seeded_client)}
    coffee = items["Ethiopia Yirgacheffe"]
    assert coffee["product_type"] == "coffee"
    assert coffee["coffee"]["region"] == "ethiopia"
    assert coffee["coffee"]["roast_level"] == "light"
    assert coffee["coffee"]["flavor_notes"]["keys"] == ["berry", "floral", "citrus"]
    assert coffee["equipment"] is None and coffee["accessory"] is None
    # A non-coffee product exposes its own attribute object instead.
    tamper = items["Distribution Tamper 58mm"]
    assert tamper["product_type"] == "accessories"
    assert tamper["accessory"]["accessory_type"] == "tamper"
    assert tamper["coffee"] is None


async def test_filter_roast_level(seeded_client: AsyncClient) -> None:
    assert _names(await _items(seeded_client, roast_level="light")) == {"Ethiopia Yirgacheffe"}


async def test_filter_region_or_within_facet(seeded_client: AsyncClient) -> None:
    names = _names(await _items(seeded_client, region="ethiopia,colombia"))
    assert names == {"Ethiopia Yirgacheffe", "Colombia Huila"}


async def test_filter_flavor_notes_or(seeded_client: AsyncClient) -> None:
    names = _names(await _items(seeded_client, flavor_notes="berry"))
    assert names == {"Ethiopia Yirgacheffe", "Kenya Nyeri AA"}


async def test_filter_acidity_bucket(seeded_client: AsyncClient) -> None:
    names = _names(await _items(seeded_client, acidity="bright"))
    assert names == {"Ethiopia Yirgacheffe", "Kenya Nyeri AA"}


async def test_filter_cross_facet_and(seeded_client: AsyncClient) -> None:
    names = _names(await _items(seeded_client, roast_level="medium", region="kenya"))
    assert names == {"Kenya Nyeri AA"}


async def test_filter_invalid_roast_returns_400(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(PRODUCTS, params={"roast_level": "burnt"})
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "CATALOG_INVALID_FILTER"


async def test_filter_inverted_range_returns_400(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(PRODUCTS, params={"body_min": 4, "body_max": 2})
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "CATALOG_INVALID_FILTER"


async def test_sort_price_ascending(seeded_client: AsyncClient) -> None:
    items = await _items(seeded_client, sort="price_asc")
    prices = [float(item["price"]) for item in items]
    assert prices == sorted(prices)


async def test_product_detail(seeded_client: AsyncClient) -> None:
    items = {item["name"]: item for item in await _items(seeded_client)}
    product_id = items["Ethiopia Yirgacheffe"]["id"]

    resp = await seeded_client.get(f"{PRODUCTS}/{product_id}")
    body = resp.json()
    assert resp.status_code == 200
    assert body["name"] == "Ethiopia Yirgacheffe"
    assert body["category_name"] == "Single Origin"
    assert body["price"] == "14.50"
    assert body["rating"] == 4.5
    assert body["rating_distribution"] == {"1": 0, "2": 0, "3": 0, "4": 1, "5": 1}
    assert "created_at" in body and "updated_at" in body


async def test_product_detail_not_found(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(f"{PRODUCTS}/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404
    assert resp.json()["error"]["error_code"] == "PRODUCT_NOT_FOUND"


async def test_search_by_name(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get("/v1/catalog/search", params={"q": "ethiopia"})
    body = resp.json()
    assert resp.status_code == 200
    assert _names(body["items"]) == {"Ethiopia Yirgacheffe"}


async def test_search_query_too_short_returns_422(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get("/v1/catalog/search", params={"q": "e"})
    assert resp.status_code == 422


async def test_list_categories(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get("/v1/catalog/categories")
    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 5
    assert "Single Origin" in {category["name"] for category in body["items"]}
