"""Individual product rating: one 1-5 star score per (user, product)."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    UUID,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from src.catalog.models.product import Product
    from src.users.models import User


class Rating(Base, TimestampMixin):
    """A single user's 1-5 star rating of a product. One per (product, user); updatable.

    The user is recorded for verification/uniqueness only and is never exposed publicly.
    """

    __tablename__ = "ratings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)

    product: Mapped["Product"] = relationship(lazy="noload")
    user: Mapped["User"] = relationship(lazy="noload")

    __table_args__ = (
        UniqueConstraint("product_id", "user_id"),
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_scale"),
        Index("idx_ratings_product_id", "product_id"),
        Index("idx_ratings_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<Rating(product={self.product_id}, user={self.user_id}, rating={self.rating})>"
