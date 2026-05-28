"""Payment error types, served through the standard AppException handlers."""

from src.api.exceptions import AppException


class PaymentException(AppException):
    """Base for payment domain errors."""


class PaymentNotFoundError(PaymentException):
    """No payment exists for the requested id or provider transaction."""

    def __init__(self, reference: str) -> None:
        super().__init__(
            f"Payment {reference} not found",
            status_code=404,
            error_code="PAYMENT_NOT_FOUND",
        )


class PaymentAccessDeniedError(PaymentException):
    """The caller is not the owner of the order being paid."""

    def __init__(self) -> None:
        super().__init__(
            "Cannot pay another user's order",
            status_code=403,
            error_code="PAYMENT_ACCESS_DENIED",
        )


class PaymentInvalidStateError(PaymentException):
    """The requested action is not allowed from the current order/payment state."""

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409, error_code="PAYMENT_INVALID_STATE")


class PaymentCallbackInvalidError(PaymentException):
    """Webhook payload signature is missing or did not verify."""

    def __init__(self, message: str = "Invalid payment callback signature") -> None:
        super().__init__(message, status_code=400, error_code="PAYMENT_CALLBACK_INVALID")


class PaymentProviderError(PaymentException):
    """The payment provider returned an error or could not be reached."""

    def __init__(self, message: str = "Payment provider error") -> None:
        super().__init__(message, status_code=502, error_code="PAYMENT_PROVIDER_ERROR")
