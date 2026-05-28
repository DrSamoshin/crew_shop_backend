"""Subscription error types, served through the standard AppException handlers."""

from src.api.exceptions import AppException


class SubscriptionException(AppException):
    """Base for subscription domain errors."""


class SubscriptionNotFoundError(SubscriptionException):
    """No subscription exists for the requested id."""

    def __init__(self, subscription_id: str) -> None:
        super().__init__(
            f"Subscription {subscription_id} not found",
            status_code=404,
            error_code="SUBSCRIPTION_NOT_FOUND",
        )


class SubscriptionAccessDeniedError(SubscriptionException):
    """The subscription belongs to another user."""

    def __init__(self) -> None:
        super().__init__(
            "Cannot access other users' subscriptions",
            status_code=403,
            error_code="SUBSCRIPTION_ACCESS_DENIED",
        )


class SubscriptionProductNotFoundError(SubscriptionException):
    """The requested product does not exist."""

    def __init__(self, product_id: str) -> None:
        super().__init__(
            f"Product {product_id} not found",
            status_code=404,
            error_code="SUBSCRIPTION_PRODUCT_NOT_FOUND",
        )


class SubscriptionProductInactiveError(SubscriptionException):
    """The requested product is inactive and cannot start a subscription."""

    def __init__(self, product_id: str) -> None:
        super().__init__(
            f"Product {product_id} is inactive",
            status_code=409,
            error_code="SUBSCRIPTION_PRODUCT_INACTIVE",
        )


class SubscriptionInvalidStateError(SubscriptionException):
    """The requested action is not allowed from the subscription's current state."""

    def __init__(self, current: str, action: str) -> None:
        super().__init__(
            f"Cannot {action} a subscription in state '{current}'",
            status_code=409,
            error_code="SUBSCRIPTION_INVALID_STATE",
        )
