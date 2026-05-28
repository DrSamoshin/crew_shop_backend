"""Integration tests for the subscription scheduler (process due, sync completed, extend)."""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.catalog.models import Category, Product, ProductType
from src.orders.enums import OrderStatus
from src.orders.models import Order
from src.subscriptions import scheduler
from src.subscriptions.enums import SubscriptionEventStatus, SubscriptionStatus
from src.subscriptions.frequency import SubscriptionFrequency
from src.subscriptions.models import (
    Subscription,
    SubscriptionDeliveryInfo,
    SubscriptionEvent,
    SubscriptionProduct,
)
from src.users.models import User


async def _seed_subscription(
    db: AsyncSession,
    *,
    frequency: SubscriptionFrequency = SubscriptionFrequency.WEEKLY,
    status: str = SubscriptionStatus.ACTIVE.value,
    event_dates: list[date] | None = None,
) -> Subscription:
    user = User(display_name="Sub")
    category = Category(name=f"c-{uuid.uuid4()}")
    product_type = ProductType(name=f"t-{uuid.uuid4()}")
    db.add_all([user, category, product_type])
    await db.flush()
    product = Product(
        name="Coffee",
        category_id=category.id,
        product_type_id=product_type.id,
        price=Decimal("12.50"),
    )
    db.add(product)
    await db.flush()

    sub = Subscription(user_id=user.id, frequency=frequency.value, status=status)
    sub.delivery_info = SubscriptionDeliveryInfo(
        recipient_name="John",
        phone="+380501234567",
        address="vul. Test 1",
        city="Kyiv",
    )
    db.add(sub)
    await db.flush()

    today = datetime.now(UTC).date()
    dates = event_dates or [today + timedelta(days=7 * i) for i in range(1, 5)]
    for scheduled in dates:
        event = SubscriptionEvent(
            subscription_id=sub.id,
            scheduled_date=scheduled,
            price_per_delivery=product.price,
        )
        db.add(event)
        await db.flush()
        db.add(
            SubscriptionProduct(
                subscription_event_id=event.id,
                product_id=product.id,
                product_name=product.name,
                product_price=product.price,
            )
        )
    await db.commit()
    return sub


async def test_process_due_event_creates_order(db_session: AsyncSession) -> None:
    today = datetime.now(UTC).date()
    sub = await _seed_subscription(
        db_session, event_dates=[today - timedelta(days=1), today + timedelta(days=7)]
    )

    processed = await scheduler.process_due_events(db_session, today=today)
    assert processed == 1

    events = (
        (
            await db_session.execute(
                select(SubscriptionEvent)
                .where(SubscriptionEvent.subscription_id == sub.id)
                .order_by(SubscriptionEvent.scheduled_date)
            )
        )
        .scalars()
        .all()
    )
    due, upcoming = events
    assert due.status == SubscriptionEventStatus.READY.value
    assert due.order_id is not None
    assert upcoming.status == SubscriptionEventStatus.PENDING.value

    order = await db_session.get(Order, due.order_id)
    assert order is not None
    assert order.order_type == "delivery"
    assert order.total_price == Decimal("12.50")


async def test_process_due_idempotent(db_session: AsyncSession) -> None:
    today = datetime.now(UTC).date()
    await _seed_subscription(
        db_session, event_dates=[today - timedelta(days=1), today + timedelta(days=7)]
    )

    first = await scheduler.process_due_events(db_session, today=today)
    second = await scheduler.process_due_events(db_session, today=today)
    assert first == 1
    assert second == 0


async def test_paused_subscription_skipped(db_session: AsyncSession) -> None:
    today = datetime.now(UTC).date()
    await _seed_subscription(
        db_session,
        status=SubscriptionStatus.PAUSED.value,
        event_dates=[today - timedelta(days=1)],
    )

    processed = await scheduler.process_due_events(db_session, today=today)
    assert processed == 0


async def test_sync_completed_events(db_session: AsyncSession) -> None:
    today = datetime.now(UTC).date()
    sub = await _seed_subscription(db_session, event_dates=[today - timedelta(days=1)])
    await scheduler.process_due_events(db_session, today=today)
    # Manually drive the linked order to completed.
    event = (
        await db_session.execute(
            select(SubscriptionEvent).where(SubscriptionEvent.subscription_id == sub.id)
        )
    ).scalar_one()
    order = await db_session.get(Order, event.order_id)
    assert order is not None
    order.status = OrderStatus.COMPLETED.value
    await db_session.flush()

    synced = await scheduler.sync_completed_events(db_session)
    assert synced == 1
    await db_session.refresh(event)
    assert event.status == SubscriptionEventStatus.COMPLETED.value

    # Re-running is idempotent.
    again = await scheduler.sync_completed_events(db_session)
    assert again == 0


async def test_extend_horizons_when_near_end(db_session: AsyncSession) -> None:
    today = datetime.now(UTC).date()
    # Two events both within the look-ahead window so the last one is < 60 days out.
    sub = await _seed_subscription(
        db_session,
        frequency=SubscriptionFrequency.WEEKLY,
        event_dates=[today + timedelta(days=7), today + timedelta(days=14)],
    )

    extended = await scheduler.extend_horizons(db_session, today=today)
    assert extended == 1

    total = await db_session.scalar(
        select(func.count())
        .select_from(SubscriptionEvent)
        .where(SubscriptionEvent.subscription_id == sub.id)
    )
    # Original 2 + a 12-event weekly horizon appended.
    assert total == 14


async def test_extend_horizons_skips_far_subscriptions(db_session: AsyncSession) -> None:
    today = datetime.now(UTC).date()
    far_dates = [today + timedelta(days=70 + 7 * i) for i in range(2)]
    await _seed_subscription(db_session, event_dates=far_dates)

    extended = await scheduler.extend_horizons(db_session, today=today)
    assert extended == 0


async def test_run_daily_summary(db_session: AsyncSession) -> None:
    today = datetime.now(UTC).date()
    # Far-out events so extension is not in play here — focus on processed/synced counters.
    await _seed_subscription(
        db_session, event_dates=[today - timedelta(days=1), today + timedelta(days=120)]
    )

    summary = await scheduler.run_daily(db_session, today=today)
    assert summary.processed_due == 1
    assert summary.synced_completed == 0
    assert summary.extended_subscriptions == 0
