"""Subscription enums. Values are the strings persisted and enforced by CHECK constraints."""

import enum

# Payment status is shared with OrderPayment; the canonical definition lives in
# ``src.payments.enums``. Re-exported here so callers that already import subscription
# enums don't need to know.
from src.payments.enums import PaymentStatus as SubscriptionPaymentStatus

__all__ = [
    "SubscriptionEventStatus",
    "SubscriptionPaymentStatus",
    "SubscriptionStatus",
]


class SubscriptionStatus(enum.StrEnum):
    """Lifecycle of a subscription (delivery-only)."""

    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class SubscriptionEventStatus(enum.StrEnum):
    """Per-event status — gates whether the underlying ``Order`` may progress."""

    PENDING = "pending"
    READY = "ready"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
