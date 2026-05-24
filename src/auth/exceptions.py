"""Auth error types, served through the standard AppException handlers."""

from src.api.exceptions import AppException


class InvalidTokenError(AppException):
    """The provider token is malformed, expired, or has a bad signature."""

    def __init__(self, message: str = "Invalid or expired token") -> None:
        super().__init__(message, status_code=401, error_code="AUTH_INVALID_TOKEN")


class ProviderVerificationFailedError(AppException):
    """The token verified cryptographically but failed a claim check (aud/iss/sub)."""

    def __init__(self, message: str = "Provider token verification failed") -> None:
        super().__init__(message, status_code=401, error_code="AUTH_PROVIDER_VERIFICATION_FAILED")


class SessionRevokedError(AppException):
    """The session is revoked, expired, or missing (e.g. after logout or refresh reuse)."""

    def __init__(self, message: str = "Session is no longer valid") -> None:
        super().__init__(message, status_code=401, error_code="AUTH_SESSION_REVOKED")


class InvalidProviderError(AppException):
    """The requested provider is not supported."""

    def __init__(self, provider: str | None = None) -> None:
        message = (
            f"Unsupported auth provider: {provider}" if provider else "Unsupported auth provider"
        )
        super().__init__(message, status_code=400, error_code="AUTH_INVALID_PROVIDER")
