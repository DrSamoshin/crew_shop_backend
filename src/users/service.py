"""User persistence and personal-account operations (profile, preferences, deletion)."""

import re
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.users.exceptions import (
    UserInvalidDisplayNameError,
    UserInvalidEmailError,
    UserInvalidPreferenceError,
    UserNotFoundError,
)
from src.users.models import User, UserPreferences
from src.users.schemas import UpdatePreferencesRequest, UpdateProfileRequest

SUPPORTED_LANGUAGES = {"en", "ru", "uk"}
DISPLAY_NAME_MAX = 255
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ------------------------------------------------------------------ validation


def _validate_display_name(value: str | None) -> None:
    if not value or not value.strip():
        raise UserInvalidDisplayNameError()
    if len(value) > DISPLAY_NAME_MAX:
        raise UserInvalidDisplayNameError("Display name too long")


def _validate_email(value: str | None) -> None:
    if value is not None and not _EMAIL_RE.match(value):
        raise UserInvalidEmailError()


def _validate_language(value: str | None) -> None:
    if value is not None and value not in SUPPORTED_LANGUAGES:
        raise UserInvalidPreferenceError("Unsupported language code")


def _validate_timezone(value: str | None) -> None:
    if value is None:
        return
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise UserInvalidPreferenceError("Unsupported timezone") from exc


# --------------------------------------------------------------------- helpers


async def create_user(
    db: AsyncSession, display_name: str, auth_user_id: uuid.UUID | None = None
) -> User:
    """Create a user with default preferences; flushed so the id is available."""
    user = User(display_name=display_name, auth_user_id=auth_user_id)
    db.add(user)
    await db.flush()
    db.add(UserPreferences(user_id=user.id))  # defaults: language=en, timezone=UTC
    await db.flush()
    return user


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def _get_preferences(db: AsyncSession, user_id: uuid.UUID) -> UserPreferences:
    prefs = await db.scalar(select(UserPreferences).where(UserPreferences.user_id == user_id))
    if prefs is None:
        raise UserNotFoundError()
    return prefs


# ----------------------------------------------------------- account operations


async def get_me(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Return the active user with preferences loaded. Raises ``USER_NOT_FOUND`` otherwise."""
    user = await db.scalar(
        select(User)
        .where(User.id == user_id, User.is_active.is_(True))
        .options(selectinload(User.preferences))
        # require_auth already loaded the User (without preferences) into this session;
        # refresh it so selectinload actually populates the relationship.
        .execution_options(populate_existing=True)
    )
    if user is None:
        raise UserNotFoundError()
    return user


async def update_profile(db: AsyncSession, user_id: uuid.UUID, data: UpdateProfileRequest) -> User:
    """Partial update of editable profile fields (only fields present in the body are applied)."""
    user = await get_me(db, user_id)
    fields = data.model_fields_set
    if "display_name" in fields:
        _validate_display_name(data.display_name)
        assert data.display_name is not None  # guaranteed by validation
        user.display_name = data.display_name.strip()
    if "email" in fields:
        _validate_email(data.email)
        user.email = data.email or None
    await db.flush()
    return user


async def update_preferences(
    db: AsyncSession, user_id: uuid.UUID, data: UpdatePreferencesRequest
) -> UserPreferences:
    """Partial update of localization preferences."""
    fields = data.model_fields_set
    if "language" in fields:
        _validate_language(data.language)
    if "timezone" in fields:
        _validate_timezone(data.timezone)
    prefs = await _get_preferences(db, user_id)
    if data.language is not None:
        prefs.language = data.language
    if data.timezone is not None:
        prefs.timezone = data.timezone
    await db.flush()
    return prefs


async def delete_account(db: AsyncSession, user_id: uuid.UUID, mode: str = "hard") -> None:
    """Soft-deactivate or hard-anonymize the account.

    Orders, subscriptions and ratings are preserved (see the User entity deletion strategies).

    Neither mode revokes the caller's crew_auth tokens — crew_auth exposes no revoke
    endpoint. Access is cut off by ``is_active``, which ``require_auth`` enforces on every
    request, so an outstanding access token stops working immediately regardless.

    A hard delete additionally detaches ``auth_user_id``. The row stays as a tombstone
    carrying the order history, and the same person signing in again lands in a genuinely
    new account rather than back inside their deleted one.
    """
    user = await get_user(db, user_id)
    if user is None or not user.is_active:
        raise UserNotFoundError()

    if mode == "soft":
        user.is_active = False
    else:
        await db.execute(delete(UserPreferences).where(UserPreferences.user_id == user_id))
        user.auth_user_id = None
        user.email = None
        user.display_name = f"User-{str(user_id)[:8]}"
        user.is_active = False
    await db.flush()
