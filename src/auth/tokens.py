"""App JWT service: mint and verify access/refresh tokens (HS256).

Stateless signing/verification only; session state (revocation, rotation) lives in
the session service. The endpoint layer delivers the refresh token via an httpOnly
cookie — this module just produces and validates the strings.
"""

import uuid
from datetime import timedelta
from typing import Any

import jwt

from src.api.core.configs import settings
from src.api.core.utils import utcnow
from src.auth.exceptions import InvalidTokenError

TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def encode_access(user_id: uuid.UUID, session_id: uuid.UUID) -> str:
    """Mint a short-lived access token carrying the user and session."""
    now = utcnow()
    claims: dict[str, Any] = {
        "type": TOKEN_TYPE_ACCESS,
        "sub": str(user_id),
        "session_id": str(session_id),
        "jti": str(uuid.uuid4()),
        "iss": settings.jwt_iss,
        "aud": settings.jwt_aud,
        "iat": now,
        "exp": now + timedelta(seconds=settings.access_token_ttl),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=settings.jwt_alg)


def encode_refresh(session_id: uuid.UUID, refresh_jti: uuid.UUID) -> str:
    """Mint a long-lived refresh token bound to a session and its current jti."""
    now = utcnow()
    claims: dict[str, Any] = {
        "type": TOKEN_TYPE_REFRESH,
        "session_id": str(session_id),
        "refresh_jti": str(refresh_jti),
        "iss": settings.jwt_iss,
        "aud": settings.jwt_aud,
        "iat": now,
        "exp": now + timedelta(seconds=settings.refresh_token_ttl),
    }
    return jwt.encode(claims, settings.secret_key, algorithm=settings.jwt_alg)


def decode(token: str, *, expected_type: str) -> dict[str, Any]:
    """Validate signature, exp, iss, aud and token type; raise AUTH_INVALID_TOKEN otherwise."""
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_alg],
            audience=settings.jwt_aud,
            issuer=settings.jwt_iss,
        )
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError() from exc

    if claims.get("type") != expected_type:
        raise InvalidTokenError("Unexpected token type")
    return claims
