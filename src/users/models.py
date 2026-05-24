"""User profile and preferences models."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import UUID, Boolean, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from src.auth.models import OAuthAccount


class User(Base, TimestampMixin):
    """User account. OAuth identity lives in OAuthAccount; users are identified by UUID.

    Email is optional and not unique (Apple privacy relay may hide or vary it).
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    oauth_account: Mapped["OAuthAccount"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
        lazy="noload",
    )
    preferences: Mapped["UserPreferences"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
        lazy="noload",
    )

    __table_args__ = (Index("idx_users_is_active", "is_active"),)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, display_name={self.display_name})>"


class UserPreferences(Base, TimestampMixin):
    """One-to-one localization preferences, created with defaults on registration."""

    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    language: Mapped[str] = mapped_column(
        String(10), nullable=False, default="en", server_default=text("'en'")
    )
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="UTC", server_default=text("'UTC'")
    )

    user: Mapped["User"] = relationship(back_populates="preferences", lazy="noload")

    def __repr__(self) -> str:
        return f"<UserPreferences(id={self.id}, user_id={self.user_id})>"
