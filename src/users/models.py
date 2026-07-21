"""User profile and preferences models."""

import uuid

from sqlalchemy import UUID, Boolean, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin


class User(Base, TimestampMixin):
    """User account, anchored to a crew_auth platform identity via ``auth_user_id``.

    ``id`` is local and never leaves crew_shop; ``auth_user_id`` is the identifier used
    at every external surface. Email is user-supplied, optional and not unique — it is
    not an identity key (crew_auth exposes none, and Apple's relay makes it unreliable).
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    # Nullable so anonymised accounts keep a tombstone row while the person is free to
    # sign up again as a genuinely new customer. Postgres allows many NULLs under UNIQUE.
    auth_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID, nullable=True, unique=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
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
