"""Payment endpoints: pay for an order (caller-authenticated) and the provider webhook.

Refunds are exposed by the service only for now; an admin refund endpoint can be added once
crew_admin needs it (a thin S2S wrapper around ``service.refund_payment``).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.auth.dependencies import require_auth
from src.payments import service
from src.payments.exceptions import PaymentCallbackInvalidError
from src.payments.provider import PaymentProviderDep
from src.payments.schemas import CallbackPayload, OrderPaymentDTO, PayOrderRequest
from src.users.models import User

router = APIRouter(tags=["payments"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(require_auth)]


@router.post(
    "/orders/{order_id}/pay",
    response_model=OrderPaymentDTO,
    summary="Initiate a charge for an order",
)
async def pay_order(
    order_id: uuid.UUID,
    db: DbDep,
    user: UserDep,
    provider: PaymentProviderDep,
    payload: PayOrderRequest | None = None,
) -> OrderPaymentDTO:
    method = payload.payment_method if payload is not None else "card"
    return await service.charge_for_order(db, provider, user.id, order_id, method)


@router.post(
    "/payments/callback",
    response_model=OrderPaymentDTO,
    summary="Payment provider webhook (signature-verified)",
)
async def payment_callback(
    request: Request,
    db: DbDep,
    provider: PaymentProviderDep,
    x_payment_signature: Annotated[str | None, Header()] = None,
) -> OrderPaymentDTO:
    raw = await request.body()
    if not provider.verify_callback(raw, x_payment_signature):
        raise PaymentCallbackInvalidError()
    payload = CallbackPayload.model_validate_json(raw)
    return await service.handle_callback(
        db, provider.name, payload.provider_transaction_id, payload.status
    )
