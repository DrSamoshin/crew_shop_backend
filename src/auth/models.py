"""OAuth account model linking a user to an external provider identity."""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    UUID,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from src.users.models import User


class OAuthAccount(Base, TimestampMixin):
    """OAuth provider identity for a user (exactly one per user).

    A user is identified on login by ``(provider, provider_id)``. ``provider_email``
    and ``provider_name`` are snapshots captured at auth time, not kept in sync.
    """

    __tablename__ = "oauth_accounts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship(back_populates="oauth_account", lazy="noload")

    __table_args__ = (
        UniqueConstraint("user_id"),  # one OAuth account per user (one-to-one)
        UniqueConstraint("provider", "provider_id"),  # one user per provider identity
        CheckConstraint("provider IN ('apple', 'google')", name="provider"),
    )

    def __repr__(self) -> str:
        return f"<OAuthAccount(id={self.id}, provider={self.provider}, user_id={self.user_id})>"


class Session(Base, TimestampMixin):
    """Server-side session backing the app's JWT tokens.

    ``id`` is the token ``session_id``; protected requests look it up to enforce
    immediate logout. ``refresh_jti`` is rotated on every refresh — a presented
    refresh whose jti does not match is a reuse, and the session is revoked.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    refresh_jti: Mapped[uuid.UUID] = mapped_column(UUID, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped["User"] = relationship(lazy="noload")

    __table_args__ = (Index("idx_sessions_user_id", "user_id"),)

    def __repr__(self) -> str:
        return f"<Session(id={self.id}, user_id={self.user_id}, is_active={self.is_active})>"
