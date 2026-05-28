"""Subscription request and response DTOs."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer

from src.subscriptions.frequency import SubscriptionFrequency

DecimalStr = Annotated[
    Decimal, PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json")
]


# --------------------------------------------------------------------- requests


class SubscriptionDeliveryIn(BaseModel):
    recipient_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=1, max_length=20)
    address: str = Field(min_length=1)
    city: str = Field(min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    notes: str | None = None


class CreateSubscriptionRequest(BaseModel):
    """Create a subscription. With ``payment_method_id`` the upfront charge runs immediately
    and the subscription activates on success; without it the subscription is left ``pending``
    until the caller posts to ``/v1/subscriptions/{id}/pay``.
    """

    product_id: uuid.UUID
    frequency: SubscriptionFrequency
    delivery: SubscriptionDeliveryIn
    payment_method_id: uuid.UUID | None = None


class PaySubscriptionRequest(BaseModel):
    """Pay a pending subscription using a saved payment method."""

    payment_method_id: uuid.UUID


# --------------------------------------------------------------------- responses


class SubscriptionEventDTO(BaseModel):
    id: uuid.UUID
    scheduled_date: date
    price_per_delivery: DecimalStr
    currency: str
    status: str
    product_name: str
    product_price: DecimalStr
    order_id: uuid.UUID | None


class SubscriptionDeliveryInfoDTO(BaseModel):
    recipient_name: str
    phone: str
    address: str
    city: str
    postal_code: str | None
    notes: str | None


class SubscriptionDTO(BaseModel):
    """Full subscription detail with the scheduled events and the captured delivery address."""

    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    total_price: DecimalStr
    currency: str
    delivery: SubscriptionDeliveryInfoDTO | None
    events: list[SubscriptionEventDTO]
    created_at: datetime
    updated_at: datetime


class SubscriptionListItemDTO(BaseModel):
    """Compact summary for the subscription list."""

    id: uuid.UUID
    status: str
    event_count: int
    total_price: DecimalStr
    next_delivery_date: date | None
    created_at: datetime


class SubscriptionListDTO(BaseModel):
    items: list[SubscriptionListItemDTO]
    total: int
