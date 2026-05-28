"""Point error types, served through the standard AppException handlers."""

from src.api.exceptions import AppException


class PointException(AppException):
    """Base for point domain errors."""


class PointNotFoundError(PointException):
    """No active coffeeshop point exists for the requested id."""

    def __init__(self, point_id: str) -> None:
        super().__init__(
            f"Pickup point {point_id} not found",
            status_code=404,
            error_code="POINT_NOT_FOUND",
        )
