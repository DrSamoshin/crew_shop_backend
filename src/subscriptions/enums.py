"""Subscription enums. Values are the strings persisted and enforced by CHECK constraints."""

import enum


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


class SubscriptionPaymentStatus(enum.StrEnum):
    """Subscription payment status — independent from the event/subscription lifecycle."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
