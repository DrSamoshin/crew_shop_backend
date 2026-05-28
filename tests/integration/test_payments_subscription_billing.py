"""Integration tests for subscription billing wired into the API and the scheduler."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.core.configs import settings as app_settings
from src.auth import sessions
from src.catalog.models import Category, Product, ProductType
from src.payments.provider import (
    ChargeRequest,
    ChargeResult,
    FakeProvider,
    RefundResult,
    get_payment_provider,
)
from src.subscriptions import scheduler
from src.subscriptions.models import (
    Subscription,
    SubscriptionEvent,
    SubscriptionPayment,
)
from src.users.models import User

Maker = async_sessionmaker[AsyncSession]


@dataclass(frozen=True, slots=True)
class Env:
    user_id: uuid.UUID
    product_id: uuid.UUID
    token: str


async def _setup(maker: Maker) -> Env:
    async with maker() as s:
        user = User(display_name="Subscriber")
        category = Category(name=f"c-{uuid.uuid4()}")
        product_type = ProductType(name=f"t-{uuid.uuid4()}")
        s.add_all([user, category, product_type])
        await s.flush()
        product = Product(
            name="Coffee",
            category_id=category.id,
            product_type_id=product_type.id,
            price=Decimal("12.50"),
        )
        s.add(product)
        await s.flush()
        access, _ = await sessions.create_session(s, user.id)
        await s.commit()
        return Env(user.id, product.id, access)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _payload(env: Env, *, frequency: str = "weekly") -> dict[str, object]:
    return {
        "product_id": str(env.product_id),
        "frequency": frequency,
        "delivery": {
            "recipient_name": "John",
            "phone": "+380501234567",
            "address": "vul. Test 1",
            "city": "Kyiv",
            "postal_code": None,
            "notes": None,
        },
    }


# --------------------------------------------------------------------- create


async def _save_method(client: AsyncClient, env: Env) -> str:
    resp = await client.post(
        "/v1/users/me/payment-methods",
        json={"intent_token": "tok"},
        headers=_auth(env.token),
    )
    assert resp.status_code == 201
    return str(resp.json()["id"])


async def test_create_subscription_charges_upfront_and_activates(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    env = await _setup(maker)
    method_id = await _save_method(client, env)
    payload = _payload(env, frequency="biweekly")
    payload["payment_method_id"] = method_id

    resp = await client.post("/v1/subscriptions", json=payload, headers=_auth(env.token))
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "active"

    async with maker() as s:
        payments = (
            (
                await s.execute(
                    select(SubscriptionPayment).where(SubscriptionPayment.user_id == env.user_id)
                )
            )
            .scalars()
            .all()
        )
        # 6 events for biweekly → 6 SubscriptionPayment rows, one per event.
        assert len(payments) == 6
        assert {p.status for p in payments} == {"completed"}
        # All share the same upfront transaction id.
        assert len({p.provider_transaction_id for p in payments}) == 1
        total_charged = sum(p.amount for p in payments)
        assert total_charged == Decimal("75.00")  # 6 * 12.50


class _FailingProvider(FakeProvider):
    async def create_charge(self, charge: ChargeRequest) -> ChargeResult:
        return ChargeResult(transaction_id=f"fake-{uuid.uuid4()}", status="failed")


async def test_create_subscription_failed_charge_blocks_activation(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    env = await _setup(maker)
    method_id = await _save_method(client, env)
    payload = _payload(env)
    payload["payment_method_id"] = method_id

    client._transport.app.dependency_overrides[get_payment_provider] = lambda: _FailingProvider()  # type: ignore[attr-defined]
    try:
        resp = await client.post("/v1/subscriptions", json=payload, headers=_auth(env.token))
    finally:
        client._transport.app.dependency_overrides.pop(get_payment_provider, None)  # type: ignore[attr-defined]
    assert resp.status_code == 409
    assert resp.json()["error"]["error_code"] == "PAYMENT_INVALID_STATE"

    async with maker() as s:
        # The exception rolls back the request transaction: no orphan subscription is left.
        sub_count = await s.scalar(
            select(func.count())
            .select_from(Subscription)
            .where(Subscription.user_id == env.user_id)
        )
        payment_count = await s.scalar(
            select(func.count())
            .select_from(SubscriptionPayment)
            .where(SubscriptionPayment.user_id == env.user_id)
        )
        assert sub_count == 0
        assert payment_count == 0


# ---------------------------------------------------------------- cancel + refund


async def test_cancel_refunds_undelivered_payments(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    env = await _setup(maker)
    method_id = await _save_method(client, env)
    payload = _payload(env, frequency="biweekly")
    payload["payment_method_id"] = method_id
    created = await client.post("/v1/subscriptions", json=payload, headers=_auth(env.token))
    sub_id = created.json()["id"]

    cancelled = await client.post(f"/v1/subscriptions/{sub_id}/cancel", headers=_auth(env.token))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    async with maker() as s:
        payments = (
            (
                await s.execute(
                    select(SubscriptionPayment).where(SubscriptionPayment.user_id == env.user_id)
                )
            )
            .scalars()
            .all()
        )
        assert {p.status for p in payments} == {"refunded"}


# ---------------------------------------------------------------- pay endpoint


async def test_pay_pending_subscription_activates(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    env = await _setup(maker)
    method_id = await _save_method(client, env)

    # Create without payment_method_id → pending, no charge yet.
    created = await client.post(
        "/v1/subscriptions",
        json=_payload(env, frequency="biweekly"),
        headers=_auth(env.token),
    )
    assert created.status_code == 201
    assert created.json()["status"] == "pending"
    sub_id = created.json()["id"]

    paid = await client.post(
        f"/v1/subscriptions/{sub_id}/pay",
        json={"payment_method_id": method_id},
        headers=_auth(env.token),
    )
    assert paid.status_code == 200
    assert paid.json()["status"] == "active"

    async with maker() as s:
        payments = (
            (
                await s.execute(
                    select(SubscriptionPayment).where(SubscriptionPayment.user_id == env.user_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(payments) == 6
        assert {p.status for p in payments} == {"completed"}


async def test_pay_when_not_pending_409(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    method_id = await _save_method(client, env)
    payload = _payload(env)
    payload["payment_method_id"] = method_id
    created = await client.post("/v1/subscriptions", json=payload, headers=_auth(env.token))
    sub_id = created.json()["id"]  # already active

    resp = await client.post(
        f"/v1/subscriptions/{sub_id}/pay",
        json={"payment_method_id": method_id},
        headers=_auth(env.token),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["error_code"] == "SUBSCRIPTION_INVALID_STATE"


async def test_pay_with_others_method_404(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup(maker)
    other = await _setup(maker)
    other_method = await _save_method(client, other)
    created = await client.post("/v1/subscriptions", json=_payload(env), headers=_auth(env.token))
    sub_id = created.json()["id"]

    resp = await client.post(
        f"/v1/subscriptions/{sub_id}/pay",
        json={"payment_method_id": other_method},
        headers=_auth(env.token),
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["error_code"] == "PAYMENT_METHOD_NOT_FOUND"


# --------------------------------------------------------- scheduler off-session


class _CountingProvider(FakeProvider):
    """FakeProvider that records charges so the test can count off-session calls."""

    def __init__(self) -> None:
        self.charges: list[ChargeRequest] = []

    async def create_charge(self, charge: ChargeRequest) -> ChargeResult:
        self.charges.append(charge)
        return ChargeResult(transaction_id=f"fake-{uuid.uuid4()}", status="completed")

    async def refund(self, provider_transaction_id: str) -> RefundResult:
        return RefundResult(status="refunded")


async def _seed_sub_for_extension(maker: Maker, today: date) -> uuid.UUID:
    async with maker() as s:
        user = User(display_name="Sub")
        category = Category(name=f"c-{uuid.uuid4()}")
        product_type = ProductType(name=f"t-{uuid.uuid4()}")
        s.add_all([user, category, product_type])
        await s.flush()
        product = Product(
            name="Coffee",
            category_id=category.id,
            product_type_id=product_type.id,
            price=Decimal("12.50"),
        )
        s.add(product)
        await s.flush()
        sub = Subscription(user_id=user.id, frequency="weekly", status="active")
        from src.subscriptions.models import SubscriptionDeliveryInfo

        sub.delivery_info = SubscriptionDeliveryInfo(
            recipient_name="John",
            phone="+380501234567",
            address="vul. T 1",
            city="Kyiv",
        )
        s.add(sub)
        await s.flush()
        # Two events in the look-ahead window so extension fires.
        for offset in (7, 14):
            event = SubscriptionEvent(
                subscription_id=sub.id,
                scheduled_date=today + timedelta(days=offset),
                price_per_delivery=product.price,
            )
            s.add(event)
            await s.flush()
            from src.subscriptions.models import SubscriptionProduct

            s.add(
                SubscriptionProduct(
                    subscription_event_id=event.id,
                    product_id=product.id,
                    product_name=product.name,
                    product_price=product.price,
                )
            )
        await s.commit()
        return sub.id


async def test_scheduler_extension_charges_off_session(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    _, maker = client_db
    today = datetime.now(UTC).date()
    sub_id = await _seed_sub_for_extension(maker, today)
    provider = _CountingProvider()

    async with maker() as s:
        extended = await scheduler.extend_horizons(s, today=today, provider=provider)
        await s.commit()
    assert extended == 1
    # Weekly horizon → 12 new events → 12 off-session charges.
    assert len(provider.charges) == 12

    async with maker() as s:
        payments = (
            (
                await s.execute(
                    select(SubscriptionPayment)
                    .join(
                        SubscriptionEvent,
                        SubscriptionEvent.id == SubscriptionPayment.subscription_event_id,
                    )
                    .where(SubscriptionEvent.subscription_id == sub_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(payments) == 12
        assert {p.status for p in payments} == {"completed"}


@pytest.fixture(autouse=True)
def _provider_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "payment_provider_secret", "test")
