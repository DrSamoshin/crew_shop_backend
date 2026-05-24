"""Integration tests for the session service and require_auth (real PostgreSQL)."""

import uuid

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import sessions, tokens
from src.auth.dependencies import require_auth
from src.auth.exceptions import InvalidTokenError, SessionRevokedError
from src.auth.models import Session
from src.users.models import User


async def _make_user(db: AsyncSession) -> User:
    user = User(display_name="Tokens Tester")
    db.add(user)
    await db.flush()
    return user


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_create_session_issues_valid_tokens(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    access, refresh = await sessions.create_session(db_session, user.id)

    claims = tokens.decode(access, expected_type=tokens.TOKEN_TYPE_ACCESS)
    assert claims["sub"] == str(user.id)
    tokens.decode(refresh, expected_type=tokens.TOKEN_TYPE_REFRESH)

    authed = await require_auth(_creds(access), db_session)
    assert authed.id == user.id


async def test_refresh_rotates_jti(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    _, refresh = await sessions.create_session(db_session, user.id)
    refresh_claims = tokens.decode(refresh, expected_type=tokens.TOKEN_TYPE_REFRESH)
    session_id = uuid.UUID(refresh_claims["session_id"])
    before = (await db_session.get(Session, session_id)).refresh_jti  # type: ignore[union-attr]

    access2, refresh2 = await sessions.refresh(db_session, refresh)
    assert refresh2 != refresh
    after = (await db_session.get(Session, session_id)).refresh_jti  # type: ignore[union-attr]
    assert after != before

    authed = await require_auth(_creds(access2), db_session)
    assert authed.id == user.id


async def test_refresh_reuse_revokes_session(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    access, refresh = await sessions.create_session(db_session, user.id)

    await sessions.refresh(db_session, refresh)  # rotate; `refresh` is now stale

    with pytest.raises(SessionRevokedError):
        await sessions.refresh(db_session, refresh)  # reuse of the old token

    # The session is revoked, so the original access token is rejected too.
    with pytest.raises(SessionRevokedError):
        await require_auth(_creds(access), db_session)


async def test_logout_invalidates_access_and_refresh(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    access, refresh = await sessions.create_session(db_session, user.id)
    access_claims = tokens.decode(access, expected_type=tokens.TOKEN_TYPE_ACCESS)
    session_id = uuid.UUID(access_claims["session_id"])

    await sessions.logout(db_session, session_id)

    with pytest.raises(SessionRevokedError):
        await require_auth(_creds(access), db_session)
    with pytest.raises(SessionRevokedError):
        await sessions.refresh(db_session, refresh)


async def test_require_auth_rejects_missing_and_invalid_tokens(db_session: AsyncSession) -> None:
    with pytest.raises(InvalidTokenError):
        await require_auth(None, db_session)
    with pytest.raises(InvalidTokenError):
        await require_auth(_creds("not-a-jwt"), db_session)
