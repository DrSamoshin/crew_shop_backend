"""Payment request and response DTOs."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer

DecimalStr = Annotated[
    Decimal, PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json")
]


class PayOrderRequest(BaseModel):
    """Optional charge metadata supplied by the client; today only ``payment_method`` is used."""

    payment_method: str = Field(default="card", min_length=1, max_length=30)


class OrderPaymentDTO(BaseModel):
    """Caller-visible view of an order payment after a charge attempt."""

    id: uuid.UUID
    order_id: uuid.UUID
    amount: DecimalStr
    currency: str
    payment_method: str
    provider: str
    provider_transaction_id: str | None
    status: str
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CallbackPayload(BaseModel):
    """The minimal shape we accept on the webhook (provider-agnostic fields)."""

    provider_transaction_id: str
    status: str  # "completed" | "failed" | "refunded"
