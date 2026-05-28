"""Subscription service: create + lifecycle (pause/resume/cancel) on top of the schema.

Billing is deferred to the Payment feature — ``SubscriptionPayment`` rows are not pre-created
here (they would break Payment's immutable-history rule once the real charge updates them);
the upcoming ``payment-subscription-billing`` task creates a payment row on the actual charge.
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.catalog.models import Product
from src.subscriptions.enums import SubscriptionEventStatus, SubscriptionStatus
from src.subscriptions.exceptions import (
    SubscriptionAccessDeniedError,
    SubscriptionInvalidStateError,
    SubscriptionNotFoundError,
    SubscriptionProductInactiveError,
    SubscriptionProductNotFoundError,
)
from src.subscriptions.frequency import event_dates
from src.subscriptions.models import (
    Subscription,
    SubscriptionDeliveryInfo,
    SubscriptionEvent,
    SubscriptionProduct,
)
from src.subscriptions.schemas import (
    CreateSubscriptionRequest,
    SubscriptionDeliveryInfoDTO,
    SubscriptionDTO,
    SubscriptionEventDTO,
    SubscriptionListDTO,
    SubscriptionListItemDTO,
)

_EVENT_OPTIONS = (
    selectinload(Subscription.delivery_info),
    selectinload(Subscription.events).selectinload(SubscriptionEvent.product),
)


def _event_dto(event: SubscriptionEvent) -> SubscriptionEventDTO:
    product = event.product
    assert product is not None  # pre-created with each event
    return SubscriptionEventDTO(
        id=event.id,
        scheduled_date=event.scheduled_date,
        price_per_delivery=event.price_per_delivery,
        currency=event.currency,
        status=event.status,
        product_name=product.product_name,
        product_price=product.product_price,
        order_id=event.order_id,
    )


def _delivery_dto(info: SubscriptionDeliveryInfo) -> SubscriptionDeliveryInfoDTO:
    return SubscriptionDeliveryInfoDTO(
        recipient_name=info.recipient_name,
        phone=info.phone,
        address=info.address,
        city=info.city,
        postal_code=info.postal_code,
        notes=info.notes,
    )


def _subscription_dto(sub: Subscription) -> SubscriptionDTO:
    events = sorted(sub.events, key=lambda e: e.scheduled_date)
    total = sum((e.price_per_delivery for e in events), Decimal("0.00"))
    return SubscriptionDTO(
        id=sub.id,
        user_id=sub.user_id,
        status=sub.status,
        total_price=total,
        currency=events[0].currency if events else "EUR",
        delivery=_delivery_dto(sub.delivery_info) if sub.delivery_info else None,
        events=[_event_dto(e) for e in events],
        created_at=sub.created_at,
        updated_at=sub.updated_at,
    )


def _list_item_dto(sub: Subscription) -> SubscriptionListItemDTO:
    events = sorted(sub.events, key=lambda e: e.scheduled_date)
    upcoming = [e for e in events if e.status in {"pending", "ready", "paused"}]
    total = sum((e.price_per_delivery for e in events), Decimal("0.00"))
    return SubscriptionListItemDTO(
        id=sub.id,
        status=sub.status,
        event_count=len(events),
        total_price=total,
        next_delivery_date=upcoming[0].scheduled_date if upcoming else None,
        created_at=sub.created_at,
    )


class SubscriptionService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------ reads

    async def _load(self, sub_id: uuid.UUID) -> Subscription | None:
        stmt = (
            select(Subscription)
            .where(Subscription.id == sub_id)
            .options(*_EVENT_OPTIONS)
            .execution_options(populate_existing=True)
        )
        return (await self._db.execute(stmt)).unique().scalar_one_or_none()

    async def _owned(self, sub_id: uuid.UUID, user_id: uuid.UUID) -> Subscription:
        sub = await self._load(sub_id)
        if sub is None:
            raise SubscriptionNotFoundError(str(sub_id))
        if sub.user_id != user_id:
            raise SubscriptionAccessDeniedError()
        return sub

    async def list_for_user(self, user_id: uuid.UUID) -> SubscriptionListDTO:
        rows = (
            (
                await self._db.execute(
                    select(Subscription)
                    .where(Subscription.user_id == user_id)
                    .options(*_EVENT_OPTIONS)
                    .order_by(Subscription.created_at.desc(), Subscription.id.desc())
                )
            )
            .unique()
            .scalars()
            .all()
        )
        items = [_list_item_dto(sub) for sub in rows]
        return SubscriptionListDTO(items=items, total=len(items))

    async def get(self, sub_id: uuid.UUID, user_id: uuid.UUID) -> SubscriptionDTO:
        return _subscription_dto(await self._owned(sub_id, user_id))

    # ------------------------------------------------------------------ create

    async def create(self, user_id: uuid.UUID, data: CreateSubscriptionRequest) -> SubscriptionDTO:
        product = await self._db.get(Product, data.product_id)
        if product is None:
            raise SubscriptionProductNotFoundError(str(data.product_id))
        if not product.is_active:
            raise SubscriptionProductInactiveError(str(data.product_id))

        today = datetime.now(UTC).date()
        sub = Subscription(user_id=user_id, status=SubscriptionStatus.ACTIVE.value)
        sub.delivery_info = SubscriptionDeliveryInfo(
            recipient_name=data.delivery.recipient_name,
            phone=data.delivery.phone,
            address=data.delivery.address,
            city=data.delivery.city,
            postal_code=data.delivery.postal_code,
            notes=data.delivery.notes,
        )
        self._db.add(sub)
        await self._db.flush()

        events: list[SubscriptionEvent] = []
        for scheduled in event_dates(today, data.frequency):
            event = SubscriptionEvent(
                subscription_id=sub.id,
                scheduled_date=scheduled,
                price_per_delivery=product.price,
            )
            self._db.add(event)
            events.append(event)
        await self._db.flush()

        for event in events:
            self._db.add(
                SubscriptionProduct(
                    subscription_event_id=event.id,
                    product_id=product.id,
                    product_name=product.name,
                    product_price=product.price,
                )
            )
        await self._db.flush()

        loaded = await self._load(sub.id)
        assert loaded is not None
        return _subscription_dto(loaded)

    # ------------------------------------------------------------- transitions

    async def pause(self, sub_id: uuid.UUID, user_id: uuid.UUID) -> SubscriptionDTO:
        sub = await self._owned(sub_id, user_id)
        if sub.status != SubscriptionStatus.ACTIVE.value:
            raise SubscriptionInvalidStateError(sub.status, "pause")
        sub.status = SubscriptionStatus.PAUSED.value
        _bulk_event_status(
            sub.events,
            old={SubscriptionEventStatus.PENDING.value},
            new=SubscriptionEventStatus.PAUSED.value,
        )
        await self._db.flush()
        return _subscription_dto(await self._reload(sub_id))

    async def resume(self, sub_id: uuid.UUID, user_id: uuid.UUID) -> SubscriptionDTO:
        sub = await self._owned(sub_id, user_id)
        if sub.status != SubscriptionStatus.PAUSED.value:
            raise SubscriptionInvalidStateError(sub.status, "resume")
        sub.status = SubscriptionStatus.ACTIVE.value
        _bulk_event_status(
            sub.events,
            old={SubscriptionEventStatus.PAUSED.value},
            new=SubscriptionEventStatus.PENDING.value,
        )
        await self._db.flush()
        return _subscription_dto(await self._reload(sub_id))

    async def cancel(self, sub_id: uuid.UUID, user_id: uuid.UUID) -> SubscriptionDTO:
        sub = await self._owned(sub_id, user_id)
        if sub.status in {
            SubscriptionStatus.CANCELLED.value,
            SubscriptionStatus.COMPLETED.value,
        }:
            raise SubscriptionInvalidStateError(sub.status, "cancel")
        sub.status = SubscriptionStatus.CANCELLED.value
        _bulk_event_status(
            sub.events,
            old={
                SubscriptionEventStatus.PENDING.value,
                SubscriptionEventStatus.PAUSED.value,
                SubscriptionEventStatus.READY.value,
            },
            new=SubscriptionEventStatus.CANCELLED.value,
        )
        await self._db.flush()
        return _subscription_dto(await self._reload(sub_id))

    async def _reload(self, sub_id: uuid.UUID) -> Subscription:
        loaded = await self._load(sub_id)
        assert loaded is not None  # just mutated in this session
        return loaded


def _bulk_event_status(events: Sequence[SubscriptionEvent], *, old: set[str], new: str) -> None:
    for event in events:
        if event.status in old:
            event.status = new
