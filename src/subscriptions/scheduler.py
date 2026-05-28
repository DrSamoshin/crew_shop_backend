"""Subscription autopilot: turn due events into delivery orders and keep horizons stocked.

Designed to be invoked from an external cron / worker. Each operation is idempotent so a
re-run on the same day is a no-op:

- ``process_due_events`` — for each ``pending`` event of an ``active`` subscription whose
  ``scheduled_date <= today`` and that has no order yet, create the delivery ``Order`` (with
  ``OrderDeliveryInfo`` cloned from the subscription's delivery address and ``OrderProduct``
  from the event's snapshot) and flip the event ``pending → ready``.
- ``sync_completed_events`` — for events whose linked order has ``status == 'completed'``,
  mark the event ``completed``. (Periodic sync instead of a cross-domain hook keeps the order
  domain decoupled from subscriptions.)
- ``extend_horizons`` — for active subscriptions whose latest event is within the look-ahead
  window, append another 3-month horizon of events + product snapshots.
- ``run_daily`` chains the three.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.core.database import async_session_maker
from src.catalog.models import Product
from src.orders.enums import OrderStatus, OrderType
from src.orders.models import Order, OrderDeliveryInfo, OrderProduct
from src.subscriptions.enums import SubscriptionEventStatus, SubscriptionStatus
from src.subscriptions.frequency import SubscriptionFrequency, next_dates_after
from src.subscriptions.models import (
    Subscription,
    SubscriptionEvent,
    SubscriptionProduct,
)

logger = logging.getLogger("src.subscriptions.scheduler")

# Extend a subscription's event horizon when its last event is within this many days.
EXTEND_LOOKAHEAD_DAYS = 60


@dataclass(frozen=True, slots=True)
class SchedulerRunSummary:
    processed_due: int
    synced_completed: int
    extended_subscriptions: int


# ------------------------------------------------------------------ due events


async def process_due_events(db: AsyncSession, *, today: date | None = None) -> int:
    """Turn due ``pending`` events into delivery orders. Returns the number processed."""
    cutoff = today or datetime.now(UTC).date()
    stmt = (
        select(SubscriptionEvent)
        .join(Subscription, Subscription.id == SubscriptionEvent.subscription_id)
        .where(
            SubscriptionEvent.status == SubscriptionEventStatus.PENDING.value,
            SubscriptionEvent.order_id.is_(None),
            SubscriptionEvent.scheduled_date <= cutoff,
            Subscription.status == SubscriptionStatus.ACTIVE.value,
        )
        .options(
            selectinload(SubscriptionEvent.subscription).selectinload(Subscription.delivery_info),
            selectinload(SubscriptionEvent.product),
        )
        .order_by(SubscriptionEvent.scheduled_date)
    )
    events = (await db.execute(stmt)).unique().scalars().all()
    count = 0
    for event in events:
        sub = event.subscription
        if sub.delivery_info is None or event.product is None:
            logger.warning(
                "scheduler: skipping event %s with missing delivery info or product snapshot",
                event.id,
            )
            continue
        order = _build_order(sub, event)
        db.add(order)
        await db.flush()
        event.order_id = order.id
        event.status = SubscriptionEventStatus.READY.value
        count += 1
    await db.flush()
    return count


def _build_order(sub: Subscription, event: SubscriptionEvent) -> Order:
    """Build a delivery ``Order`` from a subscription event's snapshot and the saved address."""
    assert sub.delivery_info is not None  # validated by the caller
    assert event.product is not None
    order = Order(
        user_id=sub.user_id,
        order_type=OrderType.DELIVERY.value,
        total_price=event.price_per_delivery,
        status=OrderStatus.CREATED.value,
    )
    order.products = [
        OrderProduct(
            product_id=event.product.product_id,
            product_name=event.product.product_name,
            product_price=event.product.product_price,
            quantity=1,
        )
    ]
    info = sub.delivery_info
    order.delivery_info = OrderDeliveryInfo(
        recipient_name=info.recipient_name,
        phone=info.phone,
        address=info.address,
        city=info.city,
        postal_code=info.postal_code,
        notes=info.notes,
    )
    return order


# ----------------------------------------------------------------- completion


async def sync_completed_events(db: AsyncSession) -> int:
    """Flip events whose linked order is ``completed`` to ``completed`` themselves."""
    stmt = (
        select(SubscriptionEvent)
        .join(Order, Order.id == SubscriptionEvent.order_id)
        .where(
            SubscriptionEvent.status != SubscriptionEventStatus.COMPLETED.value,
            Order.status == OrderStatus.COMPLETED.value,
        )
    )
    events = (await db.execute(stmt)).scalars().all()
    for event in events:
        event.status = SubscriptionEventStatus.COMPLETED.value
    await db.flush()
    return len(events)


# ----------------------------------------------------------------- extension


async def extend_horizons(db: AsyncSession, *, today: date | None = None) -> int:
    """Append a horizon's worth of events to active subscriptions running out of schedule."""
    cutoff = today or datetime.now(UTC).date()
    threshold = cutoff + timedelta(days=EXTEND_LOOKAHEAD_DAYS)

    sub_max = (
        select(
            SubscriptionEvent.subscription_id.label("subscription_id"),
            func.max(SubscriptionEvent.scheduled_date).label("last_date"),
        )
        .group_by(SubscriptionEvent.subscription_id)
        .subquery()
    )
    stmt = (
        select(Subscription, sub_max.c.last_date)
        .join(sub_max, sub_max.c.subscription_id == Subscription.id)
        .where(
            Subscription.status == SubscriptionStatus.ACTIVE.value,
            sub_max.c.last_date <= threshold,
        )
        .options(
            selectinload(Subscription.events).selectinload(SubscriptionEvent.product),
        )
    )
    rows = (await db.execute(stmt)).unique().all()
    extended = 0
    for sub, last_date in rows:
        if not await _extend_subscription(db, sub, last_date):
            continue
        extended += 1
    await db.flush()
    return extended


async def _extend_subscription(db: AsyncSession, sub: Subscription, last_date: date) -> bool:
    """Schedule the next horizon for ``sub``; returns ``False`` if extension is impossible."""
    if not sub.events:
        return False
    frequency = SubscriptionFrequency(sub.frequency)
    last_product = sub.events[-1].product
    if last_product is None:
        return False
    product = await db.get(Product, last_product.product_id)
    if product is None or not product.is_active:
        logger.info(
            "scheduler: skipping extension for subscription %s (product %s inactive/missing)",
            sub.id,
            last_product.product_id,
        )
        return False
    price = product.price
    name = product.name

    for scheduled in next_dates_after(last_date, frequency):
        event = SubscriptionEvent(
            subscription_id=sub.id,
            scheduled_date=scheduled,
            price_per_delivery=price,
        )
        db.add(event)
        await db.flush()
        db.add(
            SubscriptionProduct(
                subscription_event_id=event.id,
                product_id=product.id,
                product_name=name,
                product_price=Decimal(price),
            )
        )
    return True


# --------------------------------------------------------------------- runner


async def run_daily(db: AsyncSession, *, today: date | None = None) -> SchedulerRunSummary:
    """The full daily pass: order due events, sync completed, then extend horizons."""
    processed = await process_due_events(db, today=today)
    synced = await sync_completed_events(db)
    extended = await extend_horizons(db, today=today)
    return SchedulerRunSummary(
        processed_due=processed,
        synced_completed=synced,
        extended_subscriptions=extended,
    )


async def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    async with async_session_maker() as session:
        summary = await run_daily(session)
        await session.commit()
    logger.info(
        "scheduler done: processed=%d synced=%d extended=%d",
        summary.processed_due,
        summary.synced_completed,
        summary.extended_subscriptions,
    )


if __name__ == "__main__":
    asyncio.run(_main())
