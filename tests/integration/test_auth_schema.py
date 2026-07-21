"""Integration tests for the identity schema (users anchored to crew_auth, preferences)."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models import User, UserPreferences


async def test_create_user_with_platform_identity(db_session: AsyncSession) -> None:
    auth_user_id = uuid.uuid4()
    user = User(display_name="Alice", email="alice@example.com", auth_user_id=auth_user_id)
    db_session.add(user)
    await db_session.flush()

    prefs = UserPreferences(user_id=user.id)
    db_session.add(prefs)
    await db_session.flush()

    await db_session.refresh(user)
    await db_session.refresh(prefs)
    assert user.auth_user_id == auth_user_id
    assert user.id != auth_user_id  # the local id is generated here, not by crew_auth
    assert user.is_active is True
    assert prefs.language == "en"
    assert prefs.timezone == "UTC"


async def test_duplicate_platform_identity_rejected(db_session: AsyncSession) -> None:
    auth_user_id = uuid.uuid4()
    db_session.add(User(display_name="A", auth_user_id=auth_user_id))
    await db_session.flush()

    db_session.add(User(display_name="B", auth_user_id=auth_user_id))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_many_users_may_have_no_platform_identity(db_session: AsyncSession) -> None:
    """UNIQUE must not collapse the tombstones left behind by hard deletes."""
    db_session.add_all(
        [
            User(display_name="Detached A", auth_user_id=None),
            User(display_name="Detached B", auth_user_id=None),
        ]
    )
    await db_session.flush()  # multiple NULLs are permitted under a UNIQUE index
