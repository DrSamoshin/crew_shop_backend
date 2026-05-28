"""Payment service: charge an order, process provider callbacks, and refund.

Each charge attempt is a separate ``OrderPayment`` row (immutable history). When the provider
confirms success (synchronously here, asynchronously via the webhook in the real world) the
payment row moves ``pending → completed`` and the order transitions ``created → confirmed``.
A failed provider call moves the row to ``failed`` and leaves the order untouched. Refunds
flip the row to ``refunded`` and the order to ``refunded`` via the generic status machine.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.utils import utcnow
from src.orders.enums import OrderStatus
from src.orders.exceptions import OrderNotFoundError
from src.orders.models import Order
from src.orders.status import ensure_transition
from src.payments.enums import PaymentStatus
from src.payments.exceptions import (
    PaymentAccessDeniedError,
    PaymentInvalidStateError,
    PaymentNotFoundError,
)
from src.payments.models import OrderPayment
from src.payments.provider import ChargeRequest, PaymentProvider
from src.payments.schemas import OrderPaymentDTO


def _payment_dto(payment: OrderPayment) -> OrderPaymentDTO:
    return OrderPaymentDTO(
        id=payment.id,
        order_id=payment.order_id,
        amount=payment.amount,
        currency="EUR",
        payment_method=payment.payment_method,
        provider=payment.provider,
        provider_transaction_id=payment.provider_transaction_id,
        status=payment.status,
        completed_at=payment.completed_at,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
    )


async def charge_for_order(
    db: AsyncSession,
    provider: PaymentProvider,
    user_id: uuid.UUID,
    order_id: uuid.UUID,
    payment_method: str,
) -> OrderPaymentDTO:
    """Initiate a charge for an order. New ``OrderPayment`` row per attempt (immutable history)."""
    order = await db.get(Order, order_id)
    if order is None:
        raise OrderNotFoundError(str(order_id))
    if order.user_id != user_id:
        raise PaymentAccessDeniedError()
    if order.status != OrderStatus.CREATED.value:
        raise PaymentInvalidStateError(f"Order is in '{order.status}' state, not 'created'")

    payment = OrderPayment(
        order_id=order.id,
        user_id=user_id,
        amount=order.total_price,
        payment_method=payment_method,
        provider=provider.name,
    )
    db.add(payment)
    await db.flush()

    result = await provider.create_charge(
        ChargeRequest(
            amount=order.total_price,
            currency=order.currency,
            reference=str(payment.id),
        )
    )
    payment.provider_transaction_id = result.transaction_id
    if result.status == PaymentStatus.COMPLETED.value:
        payment.status = PaymentStatus.COMPLETED.value
        payment.completed_at = utcnow()
        ensure_transition(OrderStatus(order.status), OrderStatus.CONFIRMED)
        order.status = OrderStatus.CONFIRMED.value
    else:
        payment.status = PaymentStatus.FAILED.value
    await db.flush()
    await db.refresh(payment)
    return _payment_dto(payment)


async def handle_callback(
    db: AsyncSession,
    provider_name: str,
    provider_transaction_id: str,
    new_status: str,
) -> OrderPaymentDTO:
    """Apply a provider callback to the matching ``OrderPayment`` (idempotent)."""
    payment = await db.scalar(
        select(OrderPayment).where(
            OrderPayment.provider_transaction_id == provider_transaction_id,
            OrderPayment.provider == provider_name,
        )
    )
    if payment is None:
        raise PaymentNotFoundError(provider_transaction_id)

    # Idempotency: once the payment is terminal we don't reapply a callback.
    if payment.status in {
        PaymentStatus.COMPLETED.value,
        PaymentStatus.FAILED.value,
        PaymentStatus.REFUNDED.value,
    }:
        return _payment_dto(payment)

    order = await db.get(Order, payment.order_id)
    if order is None:  # FK is RESTRICT so this should be impossible
        raise OrderNotFoundError(str(payment.order_id))

    if new_status == PaymentStatus.COMPLETED.value:
        payment.status = PaymentStatus.COMPLETED.value
        payment.completed_at = utcnow()
        if order.status == OrderStatus.CREATED.value:
            order.status = OrderStatus.CONFIRMED.value
    elif new_status == PaymentStatus.FAILED.value:
        payment.status = PaymentStatus.FAILED.value
    else:
        raise PaymentInvalidStateError(f"Unsupported callback status: {new_status}")

    await db.flush()
    await db.refresh(payment)
    return _payment_dto(payment)


async def refund_payment(
    db: AsyncSession, provider: PaymentProvider, payment_id: uuid.UUID
) -> OrderPaymentDTO:
    """Refund a previously completed payment; flip the order to ``refunded``."""
    payment = await db.get(OrderPayment, payment_id)
    if payment is None:
        raise PaymentNotFoundError(str(payment_id))
    if payment.status != PaymentStatus.COMPLETED.value:
        raise PaymentInvalidStateError("Can only refund a completed payment")
    if payment.provider_transaction_id is None:
        raise PaymentInvalidStateError("Payment has no provider transaction id")

    result = await provider.refund(payment.provider_transaction_id)
    if result.status != PaymentStatus.REFUNDED.value:
        raise PaymentInvalidStateError("Provider refused refund")

    payment.status = PaymentStatus.REFUNDED.value
    order = await db.get(Order, payment.order_id)
    assert order is not None  # FK RESTRICT guarantees the order still exists
    ensure_transition(OrderStatus(order.status), OrderStatus.REFUNDED)
    order.status = OrderStatus.REFUNDED.value
    await db.flush()
    await db.refresh(payment)
    return _payment_dto(payment)
