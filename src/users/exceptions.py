"""User error types, served through the standard AppException handlers."""

from src.api.exceptions import AppException


class UserException(AppException):
    """Base for user domain errors."""


class UserUnauthorizedError(UserException):
    """The request is not authenticated."""

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, status_code=401, error_code="USER_UNAUTHORIZED")


class UserNotFoundError(UserException):
    """No active account exists for the caller."""

    def __init__(self, message: str = "Account not found") -> None:
        super().__init__(message, status_code=404, error_code="USER_NOT_FOUND")


class UserInvalidDisplayNameError(UserException):
    """The display name is empty or too long."""

    def __init__(self, message: str = "Display name cannot be empty") -> None:
        super().__init__(message, status_code=400, error_code="USER_INVALID_DISPLAY_NAME")


class UserInvalidEmailError(UserException):
    """The email format is invalid."""

    def __init__(self, message: str = "Email format is invalid") -> None:
        super().__init__(message, status_code=400, error_code="USER_INVALID_EMAIL")


class UserInvalidPreferenceError(UserException):
    """A preference value (language or timezone) is unsupported."""

    def __init__(self, message: str = "Unsupported preference value") -> None:
        super().__init__(message, status_code=400, error_code="USER_INVALID_PREFERENCE")
