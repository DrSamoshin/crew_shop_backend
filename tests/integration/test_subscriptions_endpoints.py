"""Integration tests for the subscription API (/v1/subscriptions)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.auth import sessions
from src.catalog.models import Category, Product, ProductType
from src.users.models import User

Maker = async_sessionmaker[AsyncSession]


@dataclass(frozen=True, slots=True)
class Env:
    user_id: uuid.UUID
    product_id: uuid.UUID
    token: str


async def _setup(maker: Maker, *, active: bool = True) -> Env:
    async with maker() as s:
        user = User(display_name="Subscriber")
        category = Category(name=f"c-{uuid.uuid4()}")
        product_type = ProductType(name=f"t-{uuid.uuid4()}")
        s.add_all([user, category, product_type])
        await s.flush()
        product = Product(
            name="Daily Coffee",
            category_id=category.id,
            product_type_id=product_type.id,
            price=Decimal("12.50"),
            is_active=active,
        )
        s.add(product)
        await s.flush()
        access, _ = await sessions.create_session(s, user.id)
        await s.commit()
        return Env(user.id, product.id, access)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _delivery() -> dict[str, object]:
    return {
        "recipient_name": "John Doe",
        "phone": "+380501234567",
        "address": "vul. Khreshchatyk 1",
        "city": "Kyiv",
        "postal_code": "01001",
        "notes": None,
    }


def _payload(env: Env, *, frequency: str = "weekly") -> dict[str, object]:
    return {
        "product_id": str(env.product_id),
        "frequency": frequency,
        "delivery": _delivery(),
    }


# --------------------------------------------------------------------- create


async def test_create_weekly_generates_12_events(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)

    resp = await client.post(
        "/v1/subscriptions", json=_payload(env, frequency="weekly"), headers=_auth(env.token)
    )
    assert resp.status_code == 201
    body = resp.json()
    # Without a saved payment method the subscription is created in ``pending``;
    # callers either pass ``payment_method_id`` in create or post to /{id}/pay later.
    assert body["status"] == "pending"
    assert body["currency"] == "EUR"
    assert len(body["events"]) == 12
    assert body["events"][0]["status"] == "pending"
    assert body["events"][0]["price_per_delivery"] == "12.50"
    # First delivery is one interval (7 days) ahead.
    today = datetime.now(UTC).date()
    first_date = datetime.strptime(body["events"][0]["scheduled_date"], "%Y-%m-%d").date()
    assert first_date == today + timedelta(days=7)
    assert body["total_price"] == "150.00"  # 12 * 12.50


async def test_create_biweekly_and_monthly_event_counts(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    env = await _setup(maker)

    bi = await client.post(
        "/v1/subscriptions", json=_payload(env, frequency="biweekly"), headers=_auth(env.token)
    )
    assert len(bi.json()["events"]) == 6

    monthly_env = await _setup(maker)
    mo = await client.post(
        "/v1/subscriptions",
        json=_payload(monthly_env, frequency="monthly"),
        headers=_auth(monthly_env.token),
    )
    assert len(mo.json()["events"]) == 3


async def test_create_inactive_product_409(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker, active=False)

    resp = await client.post("/v1/subscriptions", json=_payload(env), headers=_auth(env.token))
    assert resp.status_code == 409
    assert resp.json()["error"]["error_code"] == "SUBSCRIPTION_PRODUCT_INACTIVE"


async def test_create_unknown_product_404(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    payload = _payload(env)
    payload["product_id"] = str(uuid.uuid4())

    resp = await client.post("/v1/subscriptions", json=payload, headers=_auth(env.token))
    assert resp.status_code == 404
    assert resp.json()["error"]["error_code"] == "SUBSCRIPTION_PRODUCT_NOT_FOUND"


async def test_create_requires_auth(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    resp = await client.post("/v1/subscriptions", json=_payload(env))
    assert resp.status_code == 401


# ------------------------------------------------------------- list / detail


async def test_list_and_detail(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    created = await client.post(
        "/v1/subscriptions", json=_payload(env, frequency="biweekly"), headers=_auth(env.token)
    )
    sub_id = created.json()["id"]

    listed = await client.get("/v1/subscriptions", headers=_auth(env.token))
    assert listed.status_code == 200
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["event_count"] == 6
    assert body["items"][0]["total_price"] == "75.00"  # 6 * 12.50

    detail = await client.get(f"/v1/subscriptions/{sub_id}", headers=_auth(env.token))
    assert detail.status_code == 200
    assert detail.json()["delivery"]["city"] == "Kyiv"


async def test_detail_ownership_403(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    other = await _setup(maker)
    created = await client.post("/v1/subscriptions", json=_payload(env), headers=_auth(env.token))
    sub_id = created.json()["id"]

    resp = await client.get(f"/v1/subscriptions/{sub_id}", headers=_auth(other.token))
    assert resp.status_code == 403
    assert resp.json()["error"]["error_code"] == "SUBSCRIPTION_ACCESS_DENIED"


# --------------------------------------------------------------- lifecycle


async def test_pause_resume_cancel(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    # Save a method + create with it so the subscription activates immediately.
    method = await client.post(
        "/v1/users/me/payment-methods",
        json={"intent_token": "tok"},
        headers=_auth(env.token),
    )
    payload = _payload(env, frequency="biweekly")
    payload["payment_method_id"] = method.json()["id"]
    created = await client.post("/v1/subscriptions", json=payload, headers=_auth(env.token))
    assert created.json()["status"] == "active"
    sub_id = created.json()["id"]

    paused = await client.post(f"/v1/subscriptions/{sub_id}/pause", headers=_auth(env.token))
    assert paused.status_code == 200
    body = paused.json()
    assert body["status"] == "paused"
    assert {e["status"] for e in body["events"]} == {"paused"}

    resumed = await client.post(f"/v1/subscriptions/{sub_id}/resume", headers=_auth(env.token))
    assert resumed.json()["status"] == "active"
    assert {e["status"] for e in resumed.json()["events"]} == {"pending"}

    cancelled = await client.post(f"/v1/subscriptions/{sub_id}/cancel", headers=_auth(env.token))
    assert cancelled.json()["status"] == "cancelled"
    assert {e["status"] for e in cancelled.json()["events"]} == {"cancelled"}


async def test_pause_when_not_active_409(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    created = await client.post("/v1/subscriptions", json=_payload(env), headers=_auth(env.token))
    sub_id = created.json()["id"]
    await client.post(f"/v1/subscriptions/{sub_id}/cancel", headers=_auth(env.token))

    resp = await client.post(f"/v1/subscriptions/{sub_id}/pause", headers=_auth(env.token))
    assert resp.status_code == 409
    assert resp.json()["error"]["error_code"] == "SUBSCRIPTION_INVALID_STATE"


async def test_resume_when_not_paused_409(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    created = await client.post("/v1/subscriptions", json=_payload(env), headers=_auth(env.token))
    sub_id = created.json()["id"]

    resp = await client.post(f"/v1/subscriptions/{sub_id}/resume", headers=_auth(env.token))
    assert resp.status_code == 409
