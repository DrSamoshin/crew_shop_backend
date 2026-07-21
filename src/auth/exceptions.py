"""Auth error types, served through the standard AppException handlers.

All of these describe crew_shop's view of a crew_auth outcome. crew_auth itself answers
every failure with HTTP 400 and an ``error`` string; the mapping to meaningful status
codes happens here.
"""

from src.api.exceptions import AppException


class InvalidTokenError(AppException):
    """The access token is malformed, not signed by crew_auth, or fails a claim check."""

    def __init__(self, message: str = "Invalid access token") -> None:
        super().__init__(message, status_code=401, error_code="AUTH_INVALID_TOKEN")


class TokenExpiredError(AppException):
    """The access token is well-formed and genuine but past ``exp``.

    Distinct from ``AUTH_INVALID_TOKEN`` so the client refreshes instead of signing out.
    """

    def __init__(self, message: str = "Access token has expired") -> None:
        super().__init__(message, status_code=401, error_code="AUTH_TOKEN_EXPIRED")


class InvalidCodeError(AppException):
    """The one-time login code is unknown, expired, already used, or for another service.

    crew_auth deliberately does not distinguish these; neither do we. The client restarts
    the login redirect.
    """

    def __init__(self, message: str = "Login code is invalid or expired") -> None:
        super().__init__(message, status_code=400, error_code="AUTH_INVALID_CODE")


class InvalidRefreshTokenError(AppException):
    """crew_auth rejected the refresh token: expired, unknown, or already rotated."""

    def __init__(self, message: str = "Refresh token is invalid or expired") -> None:
        super().__init__(message, status_code=401, error_code="AUTH_INVALID_REFRESH_TOKEN")


class AccountNotFoundError(AppException):
    """The token is valid but no crew_shop account is anchored to its ``sub``.

    Happens when a platform user reaches a protected endpoint without having completed
    ``POST /v1/auth/session``, or after their account was hard-deleted and detached.
    """

    def __init__(self, message: str = "No shop account for this identity") -> None:
        super().__init__(message, status_code=401, error_code="AUTH_ACCOUNT_NOT_FOUND")


class AccountInactiveError(AppException):
    """The shop account exists but is deactivated. crew_shop's own is_active is final."""

    def __init__(self, message: str = "Account is deactivated") -> None:
        super().__init__(message, status_code=401, error_code="AUTH_ACCOUNT_INACTIVE")


class AuthUnavailableError(AppException):
    """crew_auth could not be reached or answered with a server error.

    Only raised on the paths that must talk to crew_auth (code exchange, refresh). Token
    verification is local and keeps working through a crew_auth outage.
    """

    def __init__(self, message: str = "Authentication service is unavailable") -> None:
        super().__init__(message, status_code=503, error_code="AUTH_UNAVAILABLE")
