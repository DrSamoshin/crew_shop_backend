"""Local verification of crew_auth access tokens against its published JWKS.

No network call happens on a verified request: the key set is cached at process level
for as long as crew_auth's ``Cache-Control`` allows. Four gunicorn workers means four
caches, which is fine at a five-minute max-age.
"""

import asyncio
import logging
import re
import time
import uuid
from typing import Any

import jwt

from src.auth import crew_auth
from src.auth.exceptions import (
    AuthUnavailableError,
    InvalidTokenError,
    TokenExpiredError,
)

logger = logging.getLogger(__name__)

ALGORITHM = "RS256"
DEFAULT_MAX_AGE = 300.0  # seconds, used when Cache-Control is absent or unreadable
# An unknown `kid` triggers a refetch, but a forged one must not become a way to hammer
# crew_auth — at most one refetch per window regardless of how many tokens arrive.
REFETCH_MIN_INTERVAL = 60.0  # seconds

_MAX_AGE_RE = re.compile(r"max-age\s*=\s*(\d+)")

_lock = asyncio.Lock()
_keys: dict[str, jwt.PyJWK] = {}
_expires_at: float = 0.0
# Tracked separately from the routine max-age refresh: tying the two together would
# suppress the unknown-kid refetch for a full window after every ordinary fetch, so a
# key rotation would be invisible until the cache expired anyway.
_last_refetch_at: float = float("-inf")


def reset_cache() -> None:
    """Drop the cached key set. For tests; the process otherwise never needs this."""
    global _keys, _expires_at, _last_refetch_at
    _keys = {}
    _expires_at = 0.0
    _last_refetch_at = float("-inf")


def _parse_max_age(cache_control: str | None) -> float:
    if not cache_control:
        return DEFAULT_MAX_AGE
    match = _MAX_AGE_RE.search(cache_control)
    return float(match.group(1)) if match else DEFAULT_MAX_AGE


async def _fetch_into_cache() -> None:
    """Refresh the cached key set.

    A failure is not fatal while keys are still cached: local verification exists so a
    crew_auth outage does not take authenticated traffic down with it. Only an empty
    cache turns a failure into an error the caller sees.
    """
    global _keys, _expires_at
    try:
        response = await crew_auth.fetch_jwks()
        key_set = jwt.PyJWKSet.from_dict(response.json())
    except (AuthUnavailableError, ValueError, jwt.PyJWKSetError) as exc:
        if _keys:
            logger.warning("crew_auth JWKS refresh failed, serving the cached set: %s", exc)
            return
        logger.error("crew_auth JWKS unavailable and nothing is cached: %s", exc)
        raise AuthUnavailableError("Cannot verify tokens: signing keys unavailable") from exc

    _keys = {key.key_id: key for key in key_set.keys if key.key_id}
    _expires_at = time.monotonic() + _parse_max_age(response.headers.get("cache-control"))
    logger.info("crew_auth JWKS refreshed: %d key(s)", len(_keys))


async def _get_key(kid: str) -> jwt.PyJWK:
    """Resolve a ``kid`` to its signing key, refetching when the cache cannot answer."""
    global _last_refetch_at
    async with _lock:
        if time.monotonic() >= _expires_at:
            await _fetch_into_cache()

        key = _keys.get(kid)
        if key is None and time.monotonic() - _last_refetch_at >= REFETCH_MIN_INTERVAL:
            # A key rotation the cache predates: refetch once, then accept the verdict.
            # The attempt is recorded whether or not it succeeds, so a stream of forged
            # kids costs crew_auth one request per window, not one per token.
            _last_refetch_at = time.monotonic()
            await _fetch_into_cache()
            key = _keys.get(kid)

        if key is None:
            raise InvalidTokenError("Unknown signing key")
        return key


async def verify_access_token(token: str) -> uuid.UUID:
    """Verify a crew_auth access token and return its ``sub``.

    ``iss`` and ``aud`` are deliberately not checked: crew_auth's tokens carry neither,
    and a token minted through any platform service is byte-identical to one minted
    through crew_shop. A valid signature proves the user, not the audience.
    """
    try:
        header: dict[str, Any] = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("Malformed token") from exc

    kid = header.get("kid")
    # Selecting by `kid` rather than trying every key is what lets a retired key stop
    # being trusted; crew_auth's own validator refuses tokens without one.
    if not isinstance(kid, str) or not kid:
        raise InvalidTokenError("Token carries no key id")

    key = await _get_key(kid)

    try:
        # The algorithm is pinned, never read from the header: an HS256 token signed with
        # the published public key is the standard forgery against a JWKS.
        claims: dict[str, Any] = jwt.decode(
            token,
            key=key.key,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"], "verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError() from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError() from exc

    try:
        return uuid.UUID(str(claims["sub"]))
    except ValueError as exc:
        raise InvalidTokenError("Token subject is not a user id") from exc
