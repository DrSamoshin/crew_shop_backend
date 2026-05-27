"""Order enums. Values are the exact strings persisted and enforced by CHECK constraints."""

import enum


class OrderType(enum.StrEnum):
    """Fulfillment type. Exactly one fulfillment per order (pickup XOR delivery)."""

    PICKUP = "pickup"
    DELIVERY = "delivery"


class OrderStatus(enum.StrEnum):
    """Generic order lifecycle. Pickup/delivery progress is recorded as info-table timestamps.

    ``created`` is the initial state; ``completed/cancelled/refunded/failed`` are terminal.
    """

    CREATED = "created"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    FAILED = "failed"


class GrindSize(enum.StrEnum):
    """Coffee grind sizes (coarse → fine). Non-coffee line items have ``grind = NULL``."""

    EXTRA_COARSE = "extra_coarse"
    COARSE = "coarse"
    MEDIUM_COARSE = "medium_coarse"
    MEDIUM = "medium"
    MEDIUM_FINE = "medium_fine"
    FINE = "fine"
    EXTRA_FINE = "extra_fine"
