"""Order request and response DTOs. Server-side validation is authoritative.

The detail response nests ``pickup`` and ``delivery`` objects (exactly one is set, matching
``order_type``); decimals serialize to plain strings to preserve precision.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, Field, PlainSerializer, model_validator

from src.orders.enums import GrindSize, OrderStatus, OrderType

# Decimals serialize to a plain string ("14.50") in JSON to preserve precision.
DecimalStr = Annotated[
    Decimal, PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json")
]


# --------------------------------------------------------------------- requests


class OrderItemIn(BaseModel):
    product_id: uuid.UUID
    quantity: int = Field(ge=1)
    grind: GrindSize | None = None


class DeliveryIn(BaseModel):
    recipient_name: str = Field(min_length=1, max_length=255)
    phone: str = Field(min_length=1, max_length=20)
    address: str = Field(min_length=1)
    city: str = Field(min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    delivery_notes: str | None = None


class CreateOrderRequest(BaseModel):
    order_type: OrderType
    items: list[OrderItemIn] = Field(min_length=1)
    pickup_point_id: uuid.UUID | None = None
    delivery: DeliveryIn | None = None

    @model_validator(mode="after")
    def _fulfillment_matches_type(self) -> "CreateOrderRequest":
        if self.order_type is OrderType.PICKUP:
            if self.pickup_point_id is None:
                raise ValueError("pickup_point_id is required for pickup orders")
            if self.delivery is not None:
                raise ValueError("delivery must be omitted for pickup orders")
        else:
            if self.delivery is None:
                raise ValueError("delivery is required for delivery orders")
            if self.pickup_point_id is not None:
                raise ValueError("pickup_point_id must be omitted for delivery orders")
        return self


class UpdateOrderStatusRequest(BaseModel):
    status: OrderStatus


# --------------------------------------------------------------------- responses


class OrderItemDTO(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    product_price: DecimalStr
    quantity: int
    grind: str | None
    subtotal: DecimalStr


class PickupInfoDTO(BaseModel):
    point_id: uuid.UUID
    point_name: str
    point_address: str
    pickup_code: str
    pickup_deadline: datetime
    picked_up_at: datetime | None


class DeliveryInfoDTO(BaseModel):
    recipient_name: str
    phone: str
    address: str
    city: str
    postal_code: str | None
    notes: str | None
    shipped_at: datetime | None
    delivered_at: datetime | None


class OrderDTO(BaseModel):
    """Full order detail: line items + the single fulfillment block + latest payment summary."""

    id: uuid.UUID
    user_id: uuid.UUID
    order_type: str
    status: str
    total_price: DecimalStr
    currency: str
    notes: str | None
    items: list[OrderItemDTO]
    pickup: PickupInfoDTO | None
    delivery: DeliveryInfoDTO | None
    # Latest ``OrderPayment`` rolled into the detail view so the web can render an "unpaid"
    # banner / "retry" button without a second round-trip; ``None`` if no payment was ever
    # attempted.
    payment_id: uuid.UUID | None
    payment_status: str | None
    created_at: datetime
    updated_at: datetime


class OrderListItemDTO(BaseModel):
    """Compact order summary for the history list."""

    id: uuid.UUID
    user_id: uuid.UUID
    order_type: str
    status: str
    total_price: DecimalStr
    currency: str
    item_count: int
    pickup_point_name: str | None
    delivery_city: str | None
    created_at: datetime


class OrderListDTO(BaseModel):
    items: list[OrderListItemDTO]
    total: int
    limit: int
    offset: int
