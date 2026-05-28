"""Payment enums shared by order and subscription payments."""

import enum


class PaymentStatus(enum.StrEnum):
    """Provider-driven payment lifecycle; ``failed`` and ``refunded`` are terminal.

    Independent from the parent order/subscription/event status — payment failures or refunds
    do not move the parent state.
    """

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
