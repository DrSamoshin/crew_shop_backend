"""OAuth account model linking a user to an external provider identity."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    UUID,
    CheckConstraint,
    ForeignKey,
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
