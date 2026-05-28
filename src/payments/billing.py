"""Subscription billing on top of the ``PaymentProvider`` interface.

V1 model (matches the SubscriptionPayment entity — see database/entities/subscription-payment.md):

- **Upfront** — one provider charge for the pre-created period (sum of ``price_per_delivery``);
  on success a ``SubscriptionPayment`` row is created per event (each carrying the **same**
  ``provider_transaction_id`` for reconciliation) and the subscription is activated.
- **Off-session** — when the scheduler appends new events, each gets its own provider charge
  (one ``SubscriptionPayment`` per event); a real provider needs saved-method support.
- **Refund on cancel** — undelivered events (``pending`` / ``ready`` / ``paused``) get their
  completed payments refunded. Refund is called once per distinct ``provider_transaction_id``
  to keep the upfront-charge / per-event-payment relationship honest.
"""

import uuid
from collections.abc import Iterable, Sequence
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.utils import utcnow
from src.payments.enums import PaymentStatus
from src.payments.models import PaymentMethod
from src.payments.provider import ChargeRequest, PaymentProvider
from src.subscriptions.models import (
    Subscription,
    SubscriptionEvent,
    SubscriptionPayment,
)


async def charge_subscription_upfront(
    db: AsyncSession,
    provider: PaymentProvider,
    sub: Subscription,
    *,
    method: PaymentMethod | None = None,
) -> bool:
    """Charge the period total once; on success record a completed payment per event.

    If ``method`` is supplied the charge uses the saved provider customer + token; otherwise
    it runs without saved-method context (FakeProvider works either way). Returns ``True``
    iff the provider settled the charge — the caller decides activation.
    """
    if not sub.events:
        return True  # nothing to charge — caller may activate immediately
    total = sum((e.price_per_delivery for e in sub.events), Decimal("0.00"))
    result = await provider.create_charge(
        ChargeRequest(
            amount=total,
            currency="EUR",
            reference=str(sub.id),
            customer_id=method.provider_customer_id if method else None,
            method_token=method.provider_method_token if method else None,
        )
    )
    if result.status != PaymentStatus.COMPLETED.value:
        return False
    now = utcnow()
    for event in sub.events:
        db.add(
            SubscriptionPayment(
                subscription_event_id=event.id,
                user_id=sub.user_id,
                amount=event.price_per_delivery,
                payment_method="card",
                provider=provider.name,
                provider_transaction_id=result.transaction_id,
                status=PaymentStatus.COMPLETED.value,
                completed_at=now,
            )
        )
    await db.flush()
    return True


async def charge_event_off_session(
    db: AsyncSession,
    provider: PaymentProvider,
    sub: Subscription,
    event: SubscriptionEvent,
) -> SubscriptionPayment:
    """Charge a single event on the saved method (scheduler extension path)."""
    result = await provider.create_charge(
        ChargeRequest(
            amount=event.price_per_delivery,
            currency="EUR",
            reference=f"{sub.id}:{event.id}",
            customer_id=str(sub.user_id),
        )
    )
    status = (
        PaymentStatus.COMPLETED.value
        if result.status == PaymentStatus.COMPLETED.value
        else PaymentStatus.FAILED.value
    )
    payment = SubscriptionPayment(
        subscription_event_id=event.id,
        user_id=sub.user_id,
        amount=event.price_per_delivery,
        payment_method="card",
        provider=provider.name,
        provider_transaction_id=result.transaction_id,
        status=status,
        completed_at=utcnow() if status == PaymentStatus.COMPLETED.value else None,
    )
    db.add(payment)
    await db.flush()
    return payment


async def refund_undelivered_payments(
    db: AsyncSession, provider: PaymentProvider, sub: Subscription
) -> int:
    """Refund completed payments tied to events that are still undelivered.

    Calls the provider once per distinct ``provider_transaction_id`` so an upfront charge
    backing several events is refunded once, then every payment row sharing the txn is marked
    ``refunded``. Returns the number of payment rows updated.
    """
    undelivered_event_ids: list[uuid.UUID] = [
        event.id for event in sub.events if event.status in {"pending", "paused", "ready"}
    ]
    if not undelivered_event_ids:
        return 0
    payments: Sequence[SubscriptionPayment] = (
        (
            await db.execute(
                select(SubscriptionPayment).where(
                    SubscriptionPayment.subscription_event_id.in_(undelivered_event_ids),
                    SubscriptionPayment.status == PaymentStatus.COMPLETED.value,
                )
            )
        )
        .scalars()
        .all()
    )
    return await _refund_payments(db, provider, payments)


async def _refund_payments(
    db: AsyncSession, provider: PaymentProvider, payments: Iterable[SubscriptionPayment]
) -> int:
    refunded_txns: set[str] = set()
    count = 0
    for payment in payments:
        txn_id = payment.provider_transaction_id
        if txn_id is None:
            continue
        if txn_id not in refunded_txns:
            await provider.refund(txn_id)
            refunded_txns.add(txn_id)
        payment.status = PaymentStatus.REFUNDED.value
        count += 1
    await db.flush()
    return count
