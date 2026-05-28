"""Integration tests for the subscription schema (delivery info, events, products, payments)."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.catalog.models import Category, Product, ProductType
from src.subscriptions.models import (
    Subscription,
    SubscriptionDeliveryInfo,
    SubscriptionEvent,
    SubscriptionPayment,
    SubscriptionProduct,
)
from src.users.models import User


async def _make_user(session: AsyncSession) -> User:
    user = User(display_name="Subscriber")
    session.add(user)
    await session.flush()
    return user


async def _make_product(session: AsyncSession, *, price: Decimal = Decimal("12.50")) -> Product:
    category = Category(name=f"c-{uuid.uuid4()}")
    product_type = ProductType(name=f"t-{uuid.uuid4()}")
    session.add_all([category, product_type])
    await session.flush()
    product = Product(
        name="Coffee", category_id=category.id, product_type_id=product_type.id, price=price
    )
    session.add(product)
    await session.flush()
    return product


async def _make_subscription(session: AsyncSession) -> Subscription:
    user = await _make_user(session)
    sub = Subscription(user_id=user.id, frequency="weekly")
    sub.delivery_info = SubscriptionDeliveryInfo(
        recipient_name="John Doe",
        phone="+380501234567",
        address="vul. Khreshchatyk 1",
        city="Kyiv",
        postal_code="01001",
    )
    session.add(sub)
    await session.flush()
    return sub


async def test_create_subscription_with_events_and_products(db_session: AsyncSession) -> None:
    sub = await _make_subscription(db_session)
    product = await _make_product(db_session)
    base = date(2026, 6, 1)
    events = [
        SubscriptionEvent(
            subscription_id=sub.id,
            scheduled_date=base + timedelta(days=7 * i),
            price_per_delivery=Decimal("12.50"),
        )
        for i in range(4)
    ]
    db_session.add_all(events)
    await db_session.flush()
    for ev in events:
        db_session.add(
            SubscriptionProduct(
                subscription_event_id=ev.id,
                product_id=product.id,
                product_name=product.name,
                product_price=product.price,
            )
        )
    await db_session.flush()

    await db_session.refresh(sub)
    assert sub.status == "pending"
    count = await db_session.scalar(
        select(func.count())
        .select_from(SubscriptionEvent)
        .where(SubscriptionEvent.subscription_id == sub.id)
    )
    assert count == 4


async def test_unique_event_per_date(db_session: AsyncSession) -> None:
    sub = await _make_subscription(db_session)
    day = date(2026, 6, 1)
    db_session.add(
        SubscriptionEvent(
            subscription_id=sub.id, scheduled_date=day, price_per_delivery=Decimal("12.50")
        )
    )
    await db_session.flush()
    db_session.add(
        SubscriptionEvent(
            subscription_id=sub.id, scheduled_date=day, price_per_delivery=Decimal("12.50")
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_one_delivery_info_per_subscription(db_session: AsyncSession) -> None:
    sub = await _make_subscription(db_session)
    db_session.add(
        SubscriptionDeliveryInfo(
            subscription_id=sub.id,
            recipient_name="Other",
            phone="+380501234568",
            address="2nd address",
            city="Lviv",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_one_product_per_event(db_session: AsyncSession) -> None:
    sub = await _make_subscription(db_session)
    product = await _make_product(db_session)
    event = SubscriptionEvent(
        subscription_id=sub.id, scheduled_date=date(2026, 6, 1), price_per_delivery=Decimal("12.50")
    )
    db_session.add(event)
    await db_session.flush()
    db_session.add_all(
        [
            SubscriptionProduct(
                subscription_event_id=event.id,
                product_id=product.id,
                product_name="A",
                product_price=Decimal("12.50"),
            ),
            SubscriptionProduct(
                subscription_event_id=event.id,
                product_id=product.id,
                product_name="B",
                product_price=Decimal("12.50"),
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_invalid_subscription_status_rejected(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    db_session.add(Subscription(user_id=user.id, frequency="weekly", status="renewing"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_invalid_event_status_rejected(db_session: AsyncSession) -> None:
    sub = await _make_subscription(db_session)
    db_session.add(
        SubscriptionEvent(
            subscription_id=sub.id,
            scheduled_date=date(2026, 6, 1),
            price_per_delivery=Decimal("12.50"),
            status="shipping",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_non_positive_price_rejected(db_session: AsyncSession) -> None:
    sub = await _make_subscription(db_session)
    db_session.add(
        SubscriptionEvent(
            subscription_id=sub.id,
            scheduled_date=date(2026, 6, 1),
            price_per_delivery=Decimal("0.00"),
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_delete_subscription_cascades(db_session: AsyncSession) -> None:
    sub = await _make_subscription(db_session)
    user = await _make_user(db_session)
    product = await _make_product(db_session)
    event = SubscriptionEvent(
        subscription_id=sub.id, scheduled_date=date(2026, 6, 1), price_per_delivery=Decimal("12.50")
    )
    db_session.add(event)
    await db_session.flush()
    db_session.add_all(
        [
            SubscriptionProduct(
                subscription_event_id=event.id,
                product_id=product.id,
                product_name=product.name,
                product_price=product.price,
            ),
            SubscriptionPayment(
                subscription_event_id=event.id,
                user_id=user.id,
                amount=Decimal("12.50"),
                payment_method="card",
                provider="stripe",
            ),
        ]
    )
    await db_session.flush()

    sub_id = sub.id
    await db_session.delete(sub)
    await db_session.flush()

    events_left = await db_session.scalar(
        select(func.count())
        .select_from(SubscriptionEvent)
        .where(SubscriptionEvent.subscription_id == sub_id)
    )
    delivery_left = await db_session.scalar(
        select(func.count())
        .select_from(SubscriptionDeliveryInfo)
        .where(SubscriptionDeliveryInfo.subscription_id == sub_id)
    )
    assert events_left == 0
    assert delivery_left == 0
    # Cascading via events.
    assert (await db_session.scalar(select(func.count()).select_from(SubscriptionProduct))) == 0
    assert (await db_session.scalar(select(func.count()).select_from(SubscriptionPayment))) == 0


async def test_user_delete_restricted_with_subscription(db_session: AsyncSession) -> None:
    sub = await _make_subscription(db_session)
    user = await db_session.get(User, sub.user_id)
    assert user is not None
    await db_session.delete(user)
    with pytest.raises(IntegrityError):
        await db_session.flush()
