"""Session service: create, refresh (with rotation + reuse detection), and logout.

Backs the JWT tokens with a `sessions` row so logout is immediate and stolen
refresh tokens are detected. Mutations are flushed, not committed — the request's
`get_db` dependency commits on success.
"""

import uuid
from datetime import timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.configs import settings
from src.api.core.utils import utcnow
from src.auth import tokens
from src.auth.exceptions import SessionRevokedError
from src.auth.models import Session


async def create_session(db: AsyncSession, user_id: uuid.UUID) -> tuple[str, str]:
    """Open a new session for a user and return an ``(access, refresh)`` token pair."""
    session = Session(
        user_id=user_id,
        refresh_jti=uuid.uuid4(),
        expires_at=utcnow() + timedelta(seconds=settings.refresh_token_ttl),
    )
    db.add(session)
    await db.flush()  # populate session.id
    access = tokens.encode_access(user_id, session.id)
    refresh = tokens.encode_refresh(session.id, session.refresh_jti)
    return access, refresh


async def refresh(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
    """Rotate a valid refresh token; revoke the session on reuse/expiry."""
    claims = tokens.decode(refresh_token, expected_type=tokens.TOKEN_TYPE_REFRESH)
    session = await db.get(Session, uuid.UUID(claims["session_id"]))

    if session is None or not session.is_active or session.expires_at <= utcnow():
        raise SessionRevokedError()

    if str(session.refresh_jti) != claims.get("refresh_jti"):
        # A stale/reused refresh token — revoke the whole session.
        session.is_active = False
        await db.flush()
        raise SessionRevokedError("Refresh token reuse detected")

    session.refresh_jti = uuid.uuid4()
    await db.flush()
    access = tokens.encode_access(session.user_id, session.id)
    new_refresh = tokens.encode_refresh(session.id, session.refresh_jti)
    return access, new_refresh


async def logout(db: AsyncSession, session_id: uuid.UUID) -> None:
    """Revoke a session (idempotent)."""
    session = await db.get(Session, session_id)
    if session is not None and session.is_active:
        session.is_active = False
        await db.flush()


async def revoke_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Revoke every active session for a user (full sign-out, e.g. on account deletion)."""
    await db.execute(
        update(Session)
        .where(Session.user_id == user_id, Session.is_active.is_(True))
        .values(is_active=False)
    )
    await db.flush()
