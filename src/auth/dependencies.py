"""FastAPI dependency that authenticates protected requests.

The bearer token is crew_auth's, verified locally against its JWKS. Its ``sub`` is a
platform identity, which this module resolves to the local ``User`` through
``users.auth_user_id`` — one indexed lookup, no session table, no network call.
"""

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.auth import jwks
from src.auth.exceptions import (
    AccountInactiveError,
    AccountNotFoundError,
    InvalidTokenError,
)
from src.users.models import User

_bearer = HTTPBearer(auto_error=False)


async def _resolve_user(
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
) -> User:
    """Verify the bearer access token and return the shop account behind it."""
    if credentials is None:
        raise InvalidTokenError("Missing bearer token")

    auth_user_id = await jwks.verify_access_token(credentials.credentials)

    user = await db.scalar(select(User).where(User.auth_user_id == auth_user_id))
    if user is None:
        raise AccountNotFoundError()
    # crew_auth blocks login for a deactivated platform user, but crew_shop's own flag is
    # what governs shop access and is enforced here on every request.
    if not user.is_active:
        raise AccountInactiveError()
    return user


async def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Authenticate the bearer access token and return the caller."""
    return await _resolve_user(credentials, db)


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
    return await _resolve_user(credentials, db)
