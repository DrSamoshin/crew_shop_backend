"""FastAPI dependency that authenticates protected requests."""

import uuid
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.api.core.utils import utcnow
from src.auth import tokens
from src.auth.exceptions import InvalidTokenError, SessionRevokedError
from src.auth.models import Session
from src.users.models import User

_bearer = HTTPBearer(auto_error=False)


async def _resolve_session(
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
) -> tuple[Session, User]:
    """Validate the bearer access token and return its live session + user."""
    if credentials is None:
        raise InvalidTokenError("Missing bearer token")

    claims = tokens.decode(credentials.credentials, expected_type=tokens.TOKEN_TYPE_ACCESS)

    session = await db.get(Session, uuid.UUID(claims["session_id"]))
    if session is None or not session.is_active or session.expires_at <= utcnow():
        raise SessionRevokedError()

    user = await db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise SessionRevokedError()
    return session, user


async def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Authenticate the bearer access token and return the live user.

    Enforces immediate logout: the session is looked up on every request, so a
    revoked or expired session is rejected with ``AUTH_SESSION_REVOKED``.
    """
    _, user = await _resolve_session(credentials, db)
    return user


async def require_session(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Session:
    """Like ``require_auth`` but returns the session (used by logout to revoke it)."""
    session, _ = await _resolve_session(credentials, db)
    return session


async def optional_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User | None:
    """Return the caller when authenticated, ``None`` when no token is supplied.

    Used by endpoints whose response shape varies for signed-in vs anonymous callers (catalog
    enrichment). A *present but invalid* token still raises like ``require_auth`` — silently
    accepting stale tokens would mask client bugs.
    """
    if credentials is None:
        return None
    _, user = await _resolve_session(credentials, db)
    return user
