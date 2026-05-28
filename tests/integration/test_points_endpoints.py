"""Integration tests for the public pickup-points API (/v1/points)."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.points.models import Point

Maker = async_sessionmaker[AsyncSession]


async def _make_point(
    s: AsyncSession, *, name: str, type_: str = "coffeeshop", is_active: bool = True
) -> Point:
    point = Point(
        name=name,
        address=f"{name} address",
        type=type_,
        hours={"monday": {"open": "09:00", "close": "18:00"}},
        contacts={"phone": "+380441234567", "email": "shop@crew.shop"},
        is_active=is_active,
    )
    s.add(point)
    await s.flush()
    return point


async def test_list_returns_only_active_coffeeshops(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    async with maker() as s:
        coffeeshop = await _make_point(s, name="Downtown")
        await _make_point(s, name="Warehouse Kyiv", type_="warehouse")
        await _make_point(s, name="Closed Shop", is_active=False)
        await s.commit()

    resp = await client.get("/v1/points")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(coffeeshop.id)
    assert body["items"][0]["name"] == "Downtown"
    hours = body["items"][0]["hours"]
    assert hours["monday"] == {"open": "09:00", "close": "18:00"}
    assert hours["sunday"] is None
    contacts = body["items"][0]["contacts"]
    assert contacts["phone"] == "+380441234567"
    assert contacts["email"] == "shop@crew.shop"


async def test_list_orders_by_name(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    async with maker() as s:
        await _make_point(s, name="Westside")
        await _make_point(s, name="Central")
        await s.commit()

    body = (await client.get("/v1/points")).json()
    assert [item["name"] for item in body["items"]] == ["Central", "Westside"]


async def test_detail_returns_active_coffeeshop(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    async with maker() as s:
        point = await _make_point(s, name="Downtown")
        await s.commit()
        point_id = point.id

    resp = await client.get(f"/v1/points/{point_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Downtown"


async def test_detail_404_for_unknown(client_db: tuple[AsyncClient, Maker]) -> None:
    client, _ = client_db
    resp = await client.get(f"/v1/points/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["error_code"] == "POINT_NOT_FOUND"


async def test_detail_404_for_inactive_or_non_coffeeshop(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    async with maker() as s:
        inactive = await _make_point(s, name="Closed", is_active=False)
        warehouse = await _make_point(s, name="WH", type_="warehouse")
        await s.commit()
        inactive_id = inactive.id
        warehouse_id = warehouse.id

    assert (await client.get(f"/v1/points/{inactive_id}")).status_code == 404
    assert (await client.get(f"/v1/points/{warehouse_id}")).status_code == 404
