"""Integration tests for the OrderPayment schema (provider-agnostic, EUR, immutable history)."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.catalog.models import Category, Product, ProductType
from src.orders.enums import OrderType
from src.orders.models import Order
from src.payments.models import OrderPayment
from src.users.models import User


async def _make_order(session: AsyncSession) -> Order:
    user = User(display_name="Payer")
    category = Category(name=f"c-{uuid.uuid4()}")
    product_type = ProductType(name=f"t-{uuid.uuid4()}")
    session.add_all([user, category, product_type])
    await session.flush()
    product = Product(
        name="Coffee",
        category_id=category.id,
        product_type_id=product_type.id,
        price=Decimal("12.50"),
    )
    session.add(product)
    await session.flush()
    order = Order(user_id=user.id, order_type=OrderType.PICKUP.value, total_price=Decimal("12.50"))
    session.add(order)
    await session.flush()
    return order


async def test_create_payment_defaults(db_session: AsyncSession) -> None:
    order = await _make_order(db_session)
    payment = OrderPayment(
        order_id=order.id,
        user_id=order.user_id,
        amount=Decimal("12.50"),
        payment_method="card",
        provider="stripe",
    )
    db_session.add(payment)
    await db_session.flush()
    await db_session.refresh(payment)

    assert payment.status == "pending"
    assert payment.completed_at is None
    assert payment.provider_transaction_id is None


async def test_invalid_status_rejected(db_session: AsyncSession) -> None:
    order = await _make_order(db_session)
    db_session.add(
        OrderPayment(
            order_id=order.id,
            user_id=order.user_id,
            amount=Decimal("12.50"),
            payment_method="card",
            provider="stripe",
            status="charging",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_non_positive_amount_rejected(db_session: AsyncSession) -> None:
    order = await _make_order(db_session)
    db_session.add(
        OrderPayment(
            order_id=order.id,
            user_id=order.user_id,
            amount=Decimal("0.00"),
            payment_method="card",
            provider="stripe",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_order_delete_restricted_when_paid(db_session: AsyncSession) -> None:
    order = await _make_order(db_session)
    db_session.add(
        OrderPayment(
            order_id=order.id,
            user_id=order.user_id,
            amount=Decimal("12.50"),
            payment_method="card",
            provider="stripe",
        )
    )
    await db_session.flush()
    await db_session.delete(order)
    with pytest.raises(IntegrityError):  # ON DELETE RESTRICT preserves history
        await db_session.flush()


async def test_user_delete_restricted_when_paid(db_session: AsyncSession) -> None:
    order = await _make_order(db_session)
    db_session.add(
        OrderPayment(
            order_id=order.id,
            user_id=order.user_id,
            amount=Decimal("12.50"),
            payment_method="card",
            provider="stripe",
        )
    )
    await db_session.flush()
    user = await db_session.get(User, order.user_id)
    assert user is not None
    await db_session.delete(user)
    with pytest.raises(IntegrityError):
        await db_session.flush()
