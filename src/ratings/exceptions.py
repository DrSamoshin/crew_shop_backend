"""Rating error types, served through the standard AppException handlers."""

from src.api.exceptions import AppException


class RatingException(AppException):
    """Base for rating domain errors."""


class RatingInvalidValueError(RatingException):
    """The submitted rating is outside 1..5."""

    def __init__(self, message: str = "Rating must be between 1 and 5") -> None:
        super().__init__(message, status_code=400, error_code="RATING_INVALID_VALUE")


class RatingNotPurchasedError(RatingException):
    """The caller has not completed an order containing this product."""

    def __init__(self, product_id: str) -> None:
        super().__init__(
            f"You must purchase product {product_id} to rate it",
            status_code=403,
            error_code="RATING_NOT_PURCHASED",
        )


class RatingNotFoundError(RatingException):
    """The caller has no rating to delete for this product."""

    def __init__(self, product_id: str) -> None:
        super().__init__(
            f"You have not rated product {product_id}",
            status_code=404,
            error_code="RATING_NOT_FOUND",
        )
