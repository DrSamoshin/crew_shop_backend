"""Integration tests for the public /v1/catalog endpoints against the seeded dataset."""

from typing import Any

from httpx import AsyncClient

from scripts import seed_dev

PRODUCTS = "/v1/catalog/products"

# All seeded products are active, so the catalog list total equals their seed count.
EXPECTED_PRODUCTS = (
    len(seed_dev.SEED_COFFEES)
    + len(seed_dev.SEED_EQUIPMENT)
    + len(seed_dev.SEED_ACCESSORIES)
    + len(seed_dev.SEED_CONSUMABLES)
)


async def _items(client: AsyncClient, **params: Any) -> list[dict[str, Any]]:
    """Collect every matching product across pages (the list is capped at 100 per page)."""
    collected: list[dict[str, Any]] = []
    offset = 0
    while True:
        resp = await client.get(PRODUCTS, params={"limit": 100, "offset": offset, **params})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        collected.extend(body["items"])
        offset += 100
        if offset >= body["total"]:
            break
    return collected


def _names(items: list[dict[str, Any]]) -> set[str]:
    return {item["name"] for item in items}


async def test_list_returns_all_active_products(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(PRODUCTS, params={"limit": 100})
    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == EXPECTED_PRODUCTS
    # A single page is capped at 100; the full set is reachable via pagination.
    assert len(body["items"]) == min(EXPECTED_PRODUCTS, 100)


async def test_list_pagination(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(PRODUCTS, params={"limit": 5, "offset": 0})
    body = resp.json()
    assert body["total"] == EXPECTED_PRODUCTS
    assert len(body["items"]) == 5
    assert body["limit"] == 5 and body["offset"] == 0


async def test_list_pagination_walks_every_page(seeded_client: AsyncClient) -> None:
    """Paging through the whole catalog yields each product exactly once."""
    seen: set[str] = set()
    page = 20
    offset = 0
    total = None
    while True:
        resp = await seeded_client.get(PRODUCTS, params={"limit": page, "offset": offset})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        total = body["total"]
        items = body["items"]
        assert len(items) <= page
        before = len(seen)
        seen.update(item["id"] for item in items)
        # No id repeats across pages.
        assert len(seen) == before + len(items)
        offset += page
        if offset >= total:
            break
    assert total == EXPECTED_PRODUCTS
    assert len(seen) == EXPECTED_PRODUCTS


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


async def test_list_and_detail_expose_image_url(seeded_client: AsyncClient) -> None:
    items = {item["name"]: item for item in await _items(seeded_client)}
    listed = items["Ethiopia Yirgacheffe"]
    # Seeded products carry no image; the field is present and null.
    assert "image_url" in listed and listed["image_url"] is None

    detail = (await seeded_client.get(f"{PRODUCTS}/{listed['id']}")).json()
    assert "image_url" in detail and detail["image_url"] is None


async def test_search_exposes_image_url(seeded_client: AsyncClient) -> None:
    body = (await seeded_client.get("/v1/catalog/search", params={"q": "ethiopia"})).json()
    assert body["items"]
    assert all("image_url" in item for item in body["items"])


async def test_openapi_lists_image_url_on_read_dtos(seeded_client: AsyncClient) -> None:
    schemas = (await seeded_client.get("/openapi.json")).json()["components"]["schemas"]
    assert "image_url" in schemas["ProductDTO"]["properties"]
    assert "image_url" in schemas["ProductDetailDTO"]["properties"]


async def test_search_by_name(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get("/v1/catalog/search", params={"q": "ethiopia"})
    body = resp.json()
    assert resp.status_code == 200
    assert _names(body["items"]) == {"Ethiopia Yirgacheffe"}


async def test_search_query_too_short_returns_422(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get("/v1/catalog/search", params={"q": "e"})
    assert resp.status_code == 422


async def test_list_categories(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get("/v1/catalog/product-categories")
    body = resp.json()
    assert resp.status_code == 200
    assert body["total"] == 5
    assert "Single Origin" in {category["name"] for category in body["items"]}
    # The public listing is active-only, so every item carries is_active = true.
    assert all(category["is_active"] is True for category in body["items"])


async def test_openapi_lists_category_is_active(seeded_client: AsyncClient) -> None:
    schemas = (await seeded_client.get("/openapi.json")).json()["components"]["schemas"]
    assert "is_active" in schemas["ProductCategoryDTO"]["properties"]


# ---------------------------------------------------- category-scoped, type-aware filtering

CATEGORIES = "/v1/catalog/product-categories"


async def _categories(client: AsyncClient) -> dict[str, dict[str, Any]]:
    resp = await client.get(CATEGORIES)
    assert resp.status_code == 200, resp.text
    return {category["name"]: category for category in resp.json()["items"]}


async def test_category_carries_product_type(seeded_client: AsyncClient) -> None:
    cats = await _categories(seeded_client)
    assert cats["Single Origin"]["product_type"] == "coffee"
    assert cats["Equipment"]["product_type"] == "equipment"
    assert cats["Accessories"]["product_type"] == "accessories"
    assert cats["Consumables"]["product_type"] == "consumables"


async def test_scope_by_category(seeded_client: AsyncClient) -> None:
    eq_id = (await _categories(seeded_client))["Equipment"]["id"]
    items = await _items(seeded_client, product_category_id=eq_id)
    assert items
    assert all(item["product_type"] == "equipment" for item in items)


async def test_filter_price_range(seeded_client: AsyncClient) -> None:
    items = await _items(seeded_client, price_min="100", price_max="200")
    assert items
    assert all(100 <= float(item["price"]) <= 200 for item in items)


async def test_filter_inverted_price_range_400(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(PRODUCTS, params={"price_min": "200", "price_max": "100"})
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "CATALOG_INVALID_FILTER"


async def test_filter_min_rating(seeded_client: AsyncClient) -> None:
    items = await _items(seeded_client, min_rating=4)
    assert items
    assert all(item["rating"] is not None and item["rating"] >= 4 for item in items)


async def test_filter_equipment_type_within_category(seeded_client: AsyncClient) -> None:
    eq_id = (await _categories(seeded_client))["Equipment"]["id"]
    items = await _items(seeded_client, product_category_id=eq_id, equipment_type="grinder")
    assert items
    assert all(item["equipment"]["equipment_type"] == "grinder" for item in items)


async def test_filter_material_within_equipment(seeded_client: AsyncClient) -> None:
    eq_id = (await _categories(seeded_client))["Equipment"]["id"]
    items = await _items(seeded_client, product_category_id=eq_id, material="plastic")
    assert all(item["equipment"]["material"].lower() == "plastic" for item in items)


async def test_filter_consumable_pack_range(seeded_client: AsyncClient) -> None:
    co_id = (await _categories(seeded_client))["Consumables"]["id"]
    items = await _items(seeded_client, product_category_id=co_id, pack_min=50)
    assert all(item["consumable"]["quantity_per_pack"] >= 50 for item in items)


async def test_type_facet_without_category_400(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(PRODUCTS, params={"equipment_type": "grinder"})
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "CATALOG_INVALID_FILTER"


async def test_type_facet_on_wrong_type_category_400(seeded_client: AsyncClient) -> None:
    co_id = (await _categories(seeded_client))["Single Origin"]["id"]
    resp = await seeded_client.get(
        PRODUCTS, params={"product_category_id": co_id, "equipment_type": "grinder"}
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "CATALOG_INVALID_FILTER"


async def test_material_without_category_400(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(PRODUCTS, params={"material": "plastic"})
    assert resp.status_code == 400


async def test_unknown_category_scope_400(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(
        PRODUCTS, params={"product_category_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert resp.status_code == 400


async def test_facets_coffee_category(seeded_client: AsyncClient) -> None:
    co_id = (await _categories(seeded_client))["Single Origin"]["id"]
    resp = await seeded_client.get(f"{CATEGORIES}/{co_id}/facets")
    assert resp.status_code == 200
    body = resp.json()
    assert body["product_type"] == "coffee"
    facets = {facet["key"]: facet for facet in body["facets"]}
    assert facets["region"]["kind"] == "multi"
    assert facets["region"]["options"]  # dynamic option list from data
    assert facets["body"]["kind"] == "range" and facets["body"]["min"] == 1
    assert {opt["value"] for opt in facets["acidity"]["options"]} == {"soft", "balanced", "bright"}


async def test_facets_equipment_category(seeded_client: AsyncClient) -> None:
    eq_id = (await _categories(seeded_client))["Equipment"]["id"]
    body = (await seeded_client.get(f"{CATEGORIES}/{eq_id}/facets")).json()
    assert body["product_type"] == "equipment"
    assert {facet["key"] for facet in body["facets"]} >= {
        "equipment_type",
        "material",
        "power",
        "warranty",
    }


async def test_facets_unknown_category_404(seeded_client: AsyncClient) -> None:
    resp = await seeded_client.get(f"{CATEGORIES}/00000000-0000-0000-0000-000000000000/facets")
    assert resp.status_code == 404
    assert resp.json()["error"]["error_code"] == "CATEGORY_NOT_FOUND"
