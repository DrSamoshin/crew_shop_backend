"""Integration tests for the order API (/v1/orders and /v1/admin/orders)."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.core.configs import settings as app_settings
from src.auth import sessions
from src.catalog.models import Product, ProductCategory, ProductType
from src.points.models import Point
from src.users.models import User

Maker = async_sessionmaker[AsyncSession]
ADMIN_TOKEN = "test-service-token"


@dataclass(frozen=True, slots=True)
class Env:
    user_id: uuid.UUID
    point_id: uuid.UUID
    coffee_id: uuid.UUID
    brewer_id: uuid.UUID
    token: str


async def _setup(
    maker: Maker, *, point_type: str = "coffeeshop", point_active: bool = True, active: bool = True
) -> Env:
    async with maker() as s:
        user = User(display_name="Buyer")
        point = Point(
            name="Crew Shop",
            address="addr",
            type=point_type,
            hours={},
            contacts={},
            is_active=point_active,
        )
        product_type = ProductType(name=f"t-{uuid.uuid4()}")
        category = ProductCategory(name=f"c-{uuid.uuid4()}", product_type=product_type)
        s.add_all([user, point, category, product_type])
        await s.flush()
        coffee = Product(
            name="Coffee",
            product_category_id=category.id,
            product_type_id=product_type.id,
            price=Decimal("12.50"),
            is_active=active,
        )
        brewer = Product(
            name="Brewer",
            product_category_id=category.id,
            product_type_id=product_type.id,
            price=Decimal("20.00"),
            is_active=active,
        )
        s.add_all([coffee, brewer])
        await s.flush()
        access, _ = await sessions.create_session(s, user.id)
        await s.commit()
        return Env(user.id, point.id, coffee.id, brewer.id, access)


async def _new_user_token(maker: Maker) -> str:
    async with maker() as s:
        user = User(display_name="Other")
        s.add(user)
        await s.flush()
        access, _ = await sessions.create_session(s, user.id)
        await s.commit()
        return access


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _pickup_payload(env: Env) -> dict[str, object]:
    return {
        "order_type": "pickup",
        "items": [
            {"product_id": str(env.coffee_id), "quantity": 2, "grind": "medium"},
            {"product_id": str(env.brewer_id), "quantity": 1},
        ],
        "pickup_point_id": str(env.point_id),
    }


def _delivery_payload(env: Env) -> dict[str, object]:
    return {
        "order_type": "delivery",
        "items": [{"product_id": str(env.coffee_id), "quantity": 1}],
        "delivery": {
            "recipient_name": "John Doe",
            "phone": "+380501234567",
            "address": "vul. Khreshchatyk 1",
            "city": "Kyiv",
            "postal_code": "01001",
            "delivery_notes": "leave at the door",
        },
    }


# --------------------------------------------------------------------- create


async def test_create_pickup_order(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)

    resp = await client.post("/v1/orders", json=_pickup_payload(env), headers=_auth(env.token))
    assert resp.status_code == 201
    data = resp.json()

    assert data["status"] == "created"
    assert data["order_type"] == "pickup"
    assert data["currency"] == "EUR"
    assert data["total_price"] == "45.00"  # 12.50*2 + 20.00
    assert data["delivery"] is None
    assert data["pickup"]["point_name"] == "Crew Shop"
    assert data["pickup"]["picked_up_at"] is None
    code = data["pickup"]["pickup_code"]
    assert len(code) == 6 and code.isdigit()
    assert data["pickup"]["pickup_deadline"] is not None

    coffee = next(i for i in data["items"] if i["product_name"] == "Coffee")
    assert coffee["product_price"] == "12.50"
    assert coffee["quantity"] == 2
    assert coffee["grind"] == "medium"
    assert coffee["subtotal"] == "25.00"


async def test_create_delivery_order(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)

    resp = await client.post("/v1/orders", json=_delivery_payload(env), headers=_auth(env.token))
    assert resp.status_code == 201
    data = resp.json()

    assert data["order_type"] == "delivery"
    assert data["pickup"] is None
    assert data["delivery"]["city"] == "Kyiv"
    assert data["delivery"]["notes"] == "leave at the door"
    assert data["delivery"]["shipped_at"] is None
    assert data["delivery"]["delivered_at"] is None


async def test_create_pickup_without_point_is_422(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    payload = {"order_type": "pickup", "items": [{"product_id": str(env.coffee_id), "quantity": 1}]}

    resp = await client.post("/v1/orders", json=payload, headers=_auth(env.token))
    assert resp.status_code == 422


async def test_create_unknown_product_404(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    payload = {
        "order_type": "pickup",
        "items": [{"product_id": str(uuid.uuid4()), "quantity": 1}],
        "pickup_point_id": str(env.point_id),
    }

    resp = await client.post("/v1/orders", json=payload, headers=_auth(env.token))
    assert resp.status_code == 404
    assert resp.json()["error"]["error_code"] == "ORDER_PRODUCT_NOT_FOUND"


async def test_create_inactive_product_409(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker, active=False)

    resp = await client.post("/v1/orders", json=_pickup_payload(env), headers=_auth(env.token))
    assert resp.status_code == 409
    assert resp.json()["error"]["error_code"] == "ORDER_PRODUCT_INACTIVE"


async def test_create_unavailable_pickup_point_409(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker, point_type="warehouse")  # not a coffeeshop

    resp = await client.post("/v1/orders", json=_pickup_payload(env), headers=_auth(env.token))
    assert resp.status_code == 409
    assert resp.json()["error"]["error_code"] == "ORDER_PICKUP_POINT_UNAVAILABLE"


async def test_create_requires_auth(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)

    resp = await client.post("/v1/orders", json=_pickup_payload(env))
    assert resp.status_code == 401


# ------------------------------------------------------------- list / detail


async def test_list_orders_pagination_and_filter(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    await client.post("/v1/orders", json=_pickup_payload(env), headers=_auth(env.token))
    await client.post("/v1/orders", json=_delivery_payload(env), headers=_auth(env.token))

    resp = await client.get("/v1/orders", headers=_auth(env.token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert {item["order_type"] for item in body["items"]} == {"pickup", "delivery"}
    assert all(item["item_count"] >= 1 for item in body["items"])

    created = await client.get("/v1/orders?status=created", headers=_auth(env.token))
    assert created.json()["total"] == 2
    completed = await client.get("/v1/orders?status=completed", headers=_auth(env.token))
    assert completed.json()["total"] == 0


async def test_get_order_detail_and_ownership(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    created = await client.post("/v1/orders", json=_pickup_payload(env), headers=_auth(env.token))
    order_id = created.json()["id"]

    owner = await client.get(f"/v1/orders/{order_id}", headers=_auth(env.token))
    assert owner.status_code == 200

    other_token = await _new_user_token(maker)
    forbidden = await client.get(f"/v1/orders/{order_id}", headers=_auth(other_token))
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["error_code"] == "ORDER_ACCESS_DENIED"

    missing = await client.get(f"/v1/orders/{uuid.uuid4()}", headers=_auth(env.token))
    assert missing.status_code == 404


# --------------------------------------------------------------------- cancel


async def test_cancel_only_from_created(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    created = await client.post("/v1/orders", json=_pickup_payload(env), headers=_auth(env.token))
    order_id = created.json()["id"]

    cancelled = await client.post(f"/v1/orders/{order_id}/cancel", headers=_auth(env.token))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    again = await client.post(f"/v1/orders/{order_id}/cancel", headers=_auth(env.token))
    assert again.status_code == 409
    assert again.json()["error"]["error_code"] == "ORDER_INVALID_STATUS_TRANSITION"


# --------------------------------------------------------------- admin status


def _admin_headers() -> dict[str, str]:
    return {"X-Service-Token": ADMIN_TOKEN, "X-Acting-Operator": "ops@crew.shop"}


async def test_admin_status_advances_and_sets_milestones(
    client_db: tuple[AsyncClient, Maker], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_settings, "admin_service_token", ADMIN_TOKEN)
    client, maker = client_db
    env = await _setup(maker)
    created = await client.post("/v1/orders", json=_delivery_payload(env), headers=_auth(env.token))
    order_id = created.json()["id"]

    async def _set(status: str) -> dict[str, object]:
        resp = await client.post(
            f"/v1/admin/orders/{order_id}/status", json={"status": status}, headers=_admin_headers()
        )
        assert resp.status_code == 200, resp.text
        return resp.json()

    assert (await _set("confirmed"))["status"] == "confirmed"
    in_progress = await _set("in_progress")
    assert in_progress["status"] == "in_progress"
    assert in_progress["delivery"]["shipped_at"] is not None
    completed = await _set("completed")
    assert completed["status"] == "completed"
    assert completed["delivery"]["delivered_at"] is not None


async def test_admin_status_invalid_transition_409(
    client_db: tuple[AsyncClient, Maker], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app_settings, "admin_service_token", ADMIN_TOKEN)
    client, maker = client_db
    env = await _setup(maker)
    created = await client.post("/v1/orders", json=_pickup_payload(env), headers=_auth(env.token))
    order_id = created.json()["id"]

    # created -> completed skips confirmed/in_progress.
    resp = await client.post(
        f"/v1/admin/orders/{order_id}/status",
        json={"status": "completed"},
        headers=_admin_headers(),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["error_code"] == "ORDER_INVALID_STATUS_TRANSITION"


async def test_admin_status_forbidden_without_token(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    created = await client.post("/v1/orders", json=_pickup_payload(env), headers=_auth(env.token))
    order_id = created.json()["id"]

    resp = await client.post(f"/v1/admin/orders/{order_id}/status", json={"status": "confirmed"})
    assert resp.status_code == 403
    assert resp.json()["error"]["error_code"] == "ORDER_ADMIN_FORBIDDEN"
