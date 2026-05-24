"""Integration tests for the auth identity schema (users, oauth_accounts, user_preferences)."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import OAuthAccount
from src.users.models import User, UserPreferences


async def test_create_user_with_oauth_and_preferences(db_session: AsyncSession) -> None:
    user = User(display_name="Alice", email="alice@example.com")
    db_session.add(user)
    await db_session.flush()

    db_session.add(OAuthAccount(user_id=user.id, provider="google", provider_id="google-123"))
    prefs = UserPreferences(user_id=user.id)
    db_session.add(prefs)
    await db_session.flush()

    await db_session.refresh(user)
    await db_session.refresh(prefs)
    assert user.is_active is True
    assert prefs.language == "en"
    assert prefs.timezone == "UTC"


async def test_duplicate_provider_identity_rejected(db_session: AsyncSession) -> None:
    u1 = User(display_name="A")
    u2 = User(display_name="B")
    db_session.add_all([u1, u2])
    await db_session.flush()

    db_session.add(OAuthAccount(user_id=u1.id, provider="google", provider_id="dup"))
    await db_session.flush()

    # Same (provider, provider_id) for a different user violates UNIQUE(provider, provider_id).
    db_session.add(OAuthAccount(user_id=u2.id, provider="google", provider_id="dup"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_one_oauth_account_per_user(db_session: AsyncSession) -> None:
    user = User(display_name="A")
    db_session.add(user)
    await db_session.flush()

    db_session.add(OAuthAccount(user_id=user.id, provider="google", provider_id="g-1"))
    await db_session.flush()

    # A second account for the same user violates UNIQUE(user_id) (one-to-one).
    db_session.add(OAuthAccount(user_id=user.id, provider="apple", provider_id="a-1"))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_invalid_provider_rejected(db_session: AsyncSession) -> None:
    user = User(display_name="A")
    db_session.add(user)
    await db_session.flush()

    # provider outside ('apple','google') violates the CHECK constraint.
    db_session.add(OAuthAccount(user_id=user.id, provider="facebook", provider_id="f-1"))
    with pytest.raises(IntegrityError):
        await db_session.flush()
