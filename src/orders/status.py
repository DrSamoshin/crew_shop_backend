"""Order status transition rules (generic lifecycle, shared by pickup and delivery).

The user may only cancel from ``created``; everything else is a staff/system transition.
Fulfillment progress (shipped/delivered/picked up) is recorded as info-table timestamps, not
as extra statuses.
"""

from src.orders.enums import OrderStatus
from src.orders.exceptions import OrderInvalidStatusTransitionError

# Allowed next statuses per current status. Terminal states map to an empty set.
_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.CREATED: frozenset({OrderStatus.CONFIRMED, OrderStatus.CANCELLED}),
    OrderStatus.CONFIRMED: frozenset(
        {
            OrderStatus.IN_PROGRESS,
            OrderStatus.COMPLETED,
            OrderStatus.FAILED,
            OrderStatus.REFUNDED,
        }
    ),
    OrderStatus.IN_PROGRESS: frozenset(
        {OrderStatus.COMPLETED, OrderStatus.FAILED, OrderStatus.REFUNDED}
    ),
    OrderStatus.COMPLETED: frozenset({OrderStatus.REFUNDED}),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.REFUNDED: frozenset(),
    OrderStatus.FAILED: frozenset(),
}

# Statuses a staff/system caller may set via the admin endpoint (cancel is user-only).
STAFF_TARGETS: frozenset[OrderStatus] = frozenset(
    {
        OrderStatus.CONFIRMED,
        OrderStatus.IN_PROGRESS,
        OrderStatus.COMPLETED,
        OrderStatus.FAILED,
        OrderStatus.REFUNDED,
    }
)


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    """Whether ``current -> target`` is a permitted transition."""
    return target in _TRANSITIONS.get(current, frozenset())


def ensure_transition(current: OrderStatus, target: OrderStatus) -> None:
    """Raise ``ORDER_INVALID_STATUS_TRANSITION`` unless the transition is permitted."""
    if not can_transition(current, target):
        raise OrderInvalidStatusTransitionError(current.value, target.value)
