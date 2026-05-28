"""Saved payment method request / response DTOs."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SavePaymentMethodRequest(BaseModel):
    """The frontend collected an intent/setup token from the provider; we exchange it for a
    persisted payment method. The token shape is provider-specific (FakeProvider accepts any
    non-empty string).
    """

    intent_token: str = Field(min_length=1, max_length=512)
    is_default: bool = False


class PaymentMethodDTO(BaseModel):
    """Customer-visible view of a saved payment method (no provider tokens)."""

    id: uuid.UUID
    provider: str
    brand: str
    last4: str
    exp_month: int
    exp_year: int
    is_default: bool
    created_at: datetime


class PaymentMethodListDTO(BaseModel):
    items: list[PaymentMethodDTO]
    total: int
