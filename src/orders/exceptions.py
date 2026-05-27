"""Order error types, served through the standard AppException handlers."""

from src.api.exceptions import AppException


class OrderException(AppException):
    """Base for order domain errors."""


class OrderNotFoundError(OrderException):
    """No order exists for the requested id."""

    def __init__(self, order_id: str) -> None:
        super().__init__(
            f"Order {order_id} not found",
            status_code=404,
            error_code="ORDER_NOT_FOUND",
        )


class OrderAccessDeniedError(OrderException):
    """The order belongs to another user."""

    def __init__(self) -> None:
        super().__init__(
            "Cannot access other users' orders",
            status_code=403,
            error_code="ORDER_ACCESS_DENIED",
        )


class OrderInvalidItemsError(OrderException):
    """The order has no items, or an item is malformed."""

    def __init__(self, message: str = "Order must contain at least one item") -> None:
        super().__init__(message, status_code=400, error_code="ORDER_INVALID_ITEMS")


class OrderProductNotFoundError(OrderException):
    """A referenced product does not exist."""

    def __init__(self, product_id: str) -> None:
        super().__init__(
            f"Product {product_id} not found",
            status_code=404,
            error_code="ORDER_PRODUCT_NOT_FOUND",
        )


class OrderProductInactiveError(OrderException):
    """A referenced product is inactive and cannot be ordered."""

    def __init__(self, product_id: str) -> None:
        super().__init__(
            f"Product {product_id} is inactive",
            status_code=409,
            error_code="ORDER_PRODUCT_INACTIVE",
        )


class OrderPickupPointNotFoundError(OrderException):
    """The requested pickup point does not exist."""

    def __init__(self, point_id: str) -> None:
        super().__init__(
            f"Pickup point {point_id} not found",
            status_code=404,
            error_code="ORDER_PICKUP_POINT_NOT_FOUND",
        )


class OrderPickupPointUnavailableError(OrderException):
    """The pickup point is inactive or not a coffeeshop."""

    def __init__(self, point_id: str) -> None:
        super().__init__(
            f"Pickup point {point_id} is not available",
            status_code=409,
            error_code="ORDER_PICKUP_POINT_UNAVAILABLE",
        )


class OrderInvalidStatusTransitionError(OrderException):
    """The requested status change is not allowed from the current status."""

    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            f"Cannot transition order from {current} to {target}",
            status_code=409,
            error_code="ORDER_INVALID_STATUS_TRANSITION",
        )


class OrderAdminForbiddenError(OrderException):
    """The admin S2S service credential is missing or invalid."""

    def __init__(self, message: str = "Invalid admin service credential") -> None:
        super().__init__(message, status_code=403, error_code="ORDER_ADMIN_FORBIDDEN")
