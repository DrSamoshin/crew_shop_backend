"""Integration tests for the S2S-gated points admin API (/v1/admin/points)."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.core.configs import settings as app_settings
from src.catalog.models import Category, ProductType
from src.orders.enums import OrderType
from src.orders.models import Order, OrderPickupInfo
from src.points.models import Point
from src.users.models import User

Maker = async_sessionmaker[AsyncSession]
TOKEN = "test-admin-token"


def _headers() -> dict[str, str]:
    return {"X-Service-Token": TOKEN, "X-Acting-Operator": "ops@crew.shop"}


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Downtown",
        "address": "vul. Khreshchatyk 1",
        "type": "coffeeshop",
        "hours": {"mon": {"open": "09:00", "close": "18:00"}},
        "contacts": {"phone": "+380441234567"},
        "is_active": True,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _set_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "admin_service_token", TOKEN)


async def test_create_point(client_db: tuple[AsyncClient, Maker]) -> None:
    client, _ = client_db
    resp = await client.post("/v1/admin/points", json=_payload(), headers=_headers())
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Downtown"
    assert data["type"] == "coffeeshop"
    assert data["is_active"] is True


async def test_update_point(client_db: tuple[AsyncClient, Maker]) -> None:
    client, _ = client_db
    created = await client.post("/v1/admin/points", json=_payload(), headers=_headers())
    point_id = created.json()["id"]

    updated = await client.put(
        f"/v1/admin/points/{point_id}",
        json=_payload(name="Downtown 2", is_active=False),
        headers=_headers(),
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["name"] == "Downtown 2"
    assert body["is_active"] is False


async def test_delete_unreferenced_is_hard(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    created = await client.post("/v1/admin/points", json=_payload(), headers=_headers())
    point_id = uuid.UUID(created.json()["id"])

    resp = await client.delete(f"/v1/admin/points/{point_id}", headers=_headers())
    assert resp.status_code == 204

    async with maker() as s:
        assert await s.get(Point, point_id) is None


async def _referenced_point(maker: Maker) -> uuid.UUID:
    """Seed a Point referenced by an OrderPickupInfo so delete must go soft."""
    async with maker() as s:
        user = User(display_name="Buyer")
        point = Point(name="Used", address="addr", type="coffeeshop", hours={}, contacts={})
        category = Category(name=f"c-{uuid.uuid4()}")
        product_type = ProductType(name=f"t-{uuid.uuid4()}")
        s.add_all([user, point, category, product_type])
        await s.flush()
        order = Order(
            user_id=user.id, order_type=OrderType.PICKUP.value, total_price=Decimal("10.00")
        )
        order.pickup_info = OrderPickupInfo(
            point_id=point.id,
            pickup_code="100100",
            pickup_deadline=datetime.now(UTC) + timedelta(hours=24),
        )
        s.add(order)
        await s.commit()
        return point.id


async def test_delete_referenced_auto_is_soft(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    point_id = await _referenced_point(maker)

    resp = await client.delete(f"/v1/admin/points/{point_id}", headers=_headers())
    assert resp.status_code == 204

    async with maker() as s:
        point = await s.get(Point, point_id)
        assert point is not None
        assert point.is_active is False
        # The referencing pickup info still exists.
        count = await s.scalar(
            select(func.count())
            .select_from(OrderPickupInfo)
            .where(OrderPickupInfo.point_id == point_id)
        )
        assert count == 1


async def test_delete_referenced_hard_returns_409(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    point_id = await _referenced_point(maker)

    resp = await client.delete(f"/v1/admin/points/{point_id}?mode=hard", headers=_headers())
    assert resp.status_code == 409
    assert resp.json()["error"]["error_code"] == "POINT_IN_USE"


async def test_forbidden_without_token(client_db: tuple[AsyncClient, Maker]) -> None:
    client, _ = client_db
    resp = await client.post("/v1/admin/points", json=_payload())  # no headers
    assert resp.status_code == 403
    assert resp.json()["error"]["error_code"] == "POINT_ADMIN_FORBIDDEN"


async def test_invalid_type_422(client_db: tuple[AsyncClient, Maker]) -> None:
    client, _ = client_db
    resp = await client.post("/v1/admin/points", json=_payload(type="bistro"), headers=_headers())
    assert resp.status_code == 422


async def test_write_is_audited(
    client_db: tuple[AsyncClient, Maker], caplog: pytest.LogCaptureFixture
) -> None:
    client, _ = client_db
    with caplog.at_level(logging.INFO, logger="src.points.admin.audit"):
        await client.post("/v1/admin/points", json=_payload(), headers=_headers())
    record = next(r for r in caplog.records if getattr(r, "audit", False))
    assert record.operator == "ops@crew.shop"  # type: ignore[attr-defined]
    assert record.action == "create"  # type: ignore[attr-defined]
