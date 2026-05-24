"""User persistence helpers."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models import User, UserPreferences


async def create_user(db: AsyncSession, display_name: str) -> User:
    """Create a user with default preferences; flushed so the id is available."""
    user = User(display_name=display_name)
    db.add(user)
    await db.flush()
    db.add(UserPreferences(user_id=user.id))  # defaults: language=en, timezone=UTC
    await db.flush()
    return user


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)
