"""Integration tests for the payment API (pay endpoint, webhook, service refund)."""

import json
import uuid
from dataclasses import dataclass
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.core.configs import settings as app_settings
from src.auth import sessions
from src.catalog.models import Category, Product, ProductType
from src.orders.enums import OrderType
from src.orders.models import Order, OrderProduct
from src.payments import service as payments_service
from src.payments.models import OrderPayment
from src.payments.provider import (
    ChargeRequest,
    ChargeResult,
    FakeProvider,
    PaymentProvider,
    RefundResult,
)
from src.users.models import User

Maker = async_sessionmaker[AsyncSession]
SECRET = "test-provider-secret"


@dataclass(frozen=True, slots=True)
class Env:
    user_id: uuid.UUID
    order_id: uuid.UUID
    token: str


async def _setup_order(maker: Maker) -> Env:
    async with maker() as s:
        user = User(display_name="Payer")
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
        order = Order(
            user_id=user.id, order_type=OrderType.PICKUP.value, total_price=Decimal("12.50")
        )
        order.products = [
            OrderProduct(
                product_id=product.id,
                product_name=product.name,
                product_price=product.price,
                quantity=1,
            )
        ]
        s.add(order)
        await s.flush()
        access, _ = await sessions.create_session(s, user.id)
        await s.commit()
        return Env(user.id, order.id, access)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _provider_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "payment_provider_secret", SECRET)


# --------------------------------------------------------------------- pay


async def test_pay_order_success(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup_order(maker)

    resp = await client.post(f"/v1/orders/{env.order_id}/pay", headers=_auth(env.token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["provider"] == "fake"
    assert body["provider_transaction_id"].startswith("fake-")
    assert body["completed_at"] is not None

    async with maker() as s:
        order = await s.get(Order, env.order_id)
        assert order is not None
        assert order.status == "confirmed"


class _FailingProvider(FakeProvider):
    async def create_charge(self, charge: ChargeRequest) -> ChargeResult:
        return ChargeResult(transaction_id=f"fake-{uuid.uuid4()}", status="failed")


async def test_pay_order_failure_keeps_order_created(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    env = await _setup_order(maker)

    # Override the provider for this request to force a failed charge.
    from src.api.v1.routers.payments import router  # noqa: F401 — ensures app picks up
    from src.payments.provider import get_payment_provider

    client._transport.app.dependency_overrides[get_payment_provider] = lambda: _FailingProvider()  # type: ignore[attr-defined]
    try:
        resp = await client.post(f"/v1/orders/{env.order_id}/pay", headers=_auth(env.token))
    finally:
        client._transport.app.dependency_overrides.pop(get_payment_provider, None)  # type: ignore[attr-defined]
    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"

    async with maker() as s:
        order = await s.get(Order, env.order_id)
        assert order is not None
        assert order.status == "created"  # unchanged on failure


async def test_pay_other_users_order_403(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup_order(maker)
    other = await _setup_order(maker)

    resp = await client.post(f"/v1/orders/{env.order_id}/pay", headers=_auth(other.token))
    assert resp.status_code == 403
    assert resp.json()["error"]["error_code"] == "PAYMENT_ACCESS_DENIED"


async def test_pay_order_in_wrong_state_409(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup_order(maker)
    await client.post(f"/v1/orders/{env.order_id}/pay", headers=_auth(env.token))

    second = await client.post(f"/v1/orders/{env.order_id}/pay", headers=_auth(env.token))
    assert second.status_code == 409
    assert second.json()["error"]["error_code"] == "PAYMENT_INVALID_STATE"


async def test_pay_unknown_order_404(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup_order(maker)
    resp = await client.post(f"/v1/orders/{uuid.uuid4()}/pay", headers=_auth(env.token))
    assert resp.status_code == 404
    assert resp.json()["error"]["error_code"] == "ORDER_NOT_FOUND"


# ------------------------------------------------------------------ callback


async def _seed_pending_payment(env: Env, maker: Maker) -> uuid.UUID:
    """Insert an OrderPayment(pending) referencing a known provider transaction id."""
    async with maker() as s:
        payment = OrderPayment(
            order_id=env.order_id,
            user_id=env.user_id,
            amount=Decimal("12.50"),
            payment_method="card",
            provider="fake",
            provider_transaction_id="fake-known-txn",
        )
        s.add(payment)
        await s.commit()
        return payment.id


async def test_callback_completes_payment_and_order(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    env = await _setup_order(maker)
    await _seed_pending_payment(env, maker)

    body = {"provider_transaction_id": "fake-known-txn", "status": "completed"}
    resp = await client.post(
        "/v1/payments/callback",
        content=json.dumps(body),
        headers={"X-Payment-Signature": SECRET, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"

    async with maker() as s:
        order = await s.get(Order, env.order_id)
        assert order is not None
        assert order.status == "confirmed"


async def test_callback_invalid_signature_400(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup_order(maker)
    await _seed_pending_payment(env, maker)

    body = {"provider_transaction_id": "fake-known-txn", "status": "completed"}
    resp = await client.post(
        "/v1/payments/callback",
        content=json.dumps(body),
        headers={"X-Payment-Signature": "wrong", "Content-Type": "application/json"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "PAYMENT_CALLBACK_INVALID"


async def test_callback_idempotent(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _setup_order(maker)
    await _seed_pending_payment(env, maker)
    body = {"provider_transaction_id": "fake-known-txn", "status": "completed"}
    headers = {"X-Payment-Signature": SECRET, "Content-Type": "application/json"}

    first = await client.post("/v1/payments/callback", content=json.dumps(body), headers=headers)
    second = await client.post("/v1/payments/callback", content=json.dumps(body), headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "completed"


async def test_callback_unknown_transaction_404(client_db: tuple[AsyncClient, Maker]) -> None:
    client, _ = client_db
    body = {"provider_transaction_id": "fake-missing", "status": "completed"}
    resp = await client.post(
        "/v1/payments/callback",
        content=json.dumps(body),
        headers={"X-Payment-Signature": SECRET, "Content-Type": "application/json"},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["error_code"] == "PAYMENT_NOT_FOUND"


# --------------------------------------------------------------------- refund


class _RefundingProvider(FakeProvider):
    async def refund(self, provider_transaction_id: str) -> RefundResult:
        return RefundResult(status="refunded")


async def test_refund_service_flips_payment_and_order(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    env = await _setup_order(maker)
    pay = await client.post(f"/v1/orders/{env.order_id}/pay", headers=_auth(env.token))
    payment_id = uuid.UUID(pay.json()["id"])

    provider: PaymentProvider = _RefundingProvider()
    async with maker() as s:
        result = await payments_service.refund_payment(s, provider, payment_id)
        await s.commit()
    assert result.status == "refunded"

    async with maker() as s:
        order = await s.get(Order, env.order_id)
        payment = await s.get(OrderPayment, payment_id)
        assert order is not None and payment is not None
        assert order.status == "refunded"
        assert payment.status == "refunded"
