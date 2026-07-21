"""Server-to-server client for crew_auth.

Covers the three calls crew_shop makes: exchanging a one-time login code, proxying a
refresh, and fetching the JWKS. Token *verification* is local and lives in
``src.auth.jwks`` — nothing here runs on the hot path of an authenticated request.

crew_auth answers every failure with HTTP 400 and ``{"error": ..., "message": ...}``.
Only the two error codes crew_shop can act on are mapped to meaningful responses; any
other failure, drift or transport error becomes ``AUTH_UNAVAILABLE`` so a crew_auth
problem never surfaces as a crew_shop 500.
"""

import logging
import uuid
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from src.api.core.configs import settings
from src.auth.exceptions import (
    AuthUnavailableError,
    InvalidCodeError,
    InvalidRefreshTokenError,
)

logger = logging.getLogger(__name__)

EXCHANGE_PATH = "/oauth/exchange"
REFRESH_PATH = "/refresh-token"
JWKS_PATH = "/.well-known/jwks.json"

_client: httpx.AsyncClient | None = None


class ExchangedTokens(BaseModel):
    """Response of ``POST /oauth/exchange``. ``user_id`` is the platform-wide identity."""

    access_token: str
    refresh_token: str
    user_id: uuid.UUID
    expires_in: int


class RefreshedTokens(BaseModel):
    """Response of ``POST /refresh-token``. Carries no ``user_id``, unlike the exchange."""

    access_token: str
    refresh_token: str
    expires_in: int


def get_client() -> httpx.AsyncClient:
    """Return the shared client, creating it on first use.

    Kept at module level so connections are pooled across requests. Tests replace it
    with one wired to a mock transport.
    """
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.crew_auth_url.rstrip("/"),
            timeout=settings.crew_auth_timeout,
        )
    return _client


def set_client(client: httpx.AsyncClient | None) -> None:
    """Install (or clear) the shared client. For tests and for the lifespan shutdown."""
    global _client
    _client = client


async def close_client() -> None:
    """Close the shared client, if one was created. Called from the app lifespan."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _error_code(response: httpx.Response) -> str:
    """Read crew_auth's ``error`` discriminator, tolerating a non-JSON body."""
    try:
        body = response.json()
    except ValueError:
        return ""
    return str(body.get("error", "")) if isinstance(body, dict) else ""


async def _post(path: str, payload: dict[str, Any]) -> httpx.Response:
    try:
        return await get_client().post(path, json=payload)
    except httpx.HTTPError as exc:
        logger.error("crew_auth %s unreachable: %s", path, exc)
        raise AuthUnavailableError() from exc


def _unexpected(path: str, response: httpx.Response) -> AuthUnavailableError:
    logger.error(
        "crew_auth %s returned an unexpected response: status=%s error=%s",
        path,
        response.status_code,
        _error_code(response) or "<none>",
    )
    return AuthUnavailableError()


async def exchange_code(code: str) -> ExchangedTokens:
    """Redeem a one-time login code for a token pair and the platform user id.

    The code lives 60 seconds and works once, so this is called on arrival and never
    retried — a retry can only ever fail.
    """
    response = await _post(
        EXCHANGE_PATH, {"code": code, "service_name": settings.crew_auth_service_name}
    )
    if response.status_code == httpx.codes.OK:
        try:
            return ExchangedTokens.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            logger.error("crew_auth %s returned an unreadable body: %s", EXCHANGE_PATH, exc)
            raise AuthUnavailableError() from exc
    if _error_code(response) == "invalid_code":
        raise InvalidCodeError()
    raise _unexpected(EXCHANGE_PATH, response)


async def refresh_tokens(refresh_token: str) -> RefreshedTokens:
    """Exchange a refresh token for a rotated pair. The presented token is revoked."""
    response = await _post(REFRESH_PATH, {"refresh_token": refresh_token})
    if response.status_code == httpx.codes.OK:
        try:
            return RefreshedTokens.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            logger.error("crew_auth %s returned an unreadable body: %s", REFRESH_PATH, exc)
            raise AuthUnavailableError() from exc
    if _error_code(response) == "invalid_refresh_token":
        raise InvalidRefreshTokenError()
    raise _unexpected(REFRESH_PATH, response)


async def fetch_jwks() -> httpx.Response:
    """Fetch the raw JWKS response; the caller reads both the body and Cache-Control."""
    try:
        response = await get_client().get(JWKS_PATH)
    except httpx.HTTPError as exc:
        logger.error("crew_auth %s unreachable: %s", JWKS_PATH, exc)
        raise AuthUnavailableError() from exc
    if response.status_code != httpx.codes.OK:
        raise _unexpected(JWKS_PATH, response)
    return response
