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


class PointInUseError(PointException):
    """A hard delete was attempted on a point still referenced by orders."""

    def __init__(self, point_id: str) -> None:
        super().__init__(
            f"Pickup point {point_id} is referenced by existing orders",
            status_code=409,
            error_code="POINT_IN_USE",
        )


class PointAdminForbiddenError(PointException):
    """The admin S2S service credential is missing or invalid."""

    def __init__(self, message: str = "Invalid admin service credential") -> None:
        super().__init__(message, status_code=403, error_code="POINT_ADMIN_FORBIDDEN")
