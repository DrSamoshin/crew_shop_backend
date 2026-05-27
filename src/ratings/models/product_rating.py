"""Denormalized per-product rating aggregate, recomputed from the Rating rows.

A row exists only for products that have at least one rating, so ``average_rating`` is
always a valid 1.0-5.0 value. Products with no ratings simply have no aggregate row.
"""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    UUID,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from src.catalog.models.product import Product


class ProductRating(Base, TimestampMixin):
    """Aggregate of a product's ratings: simple average, count, and per-star distribution."""

    __tablename__ = "product_ratings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    average_rating: Mapped[Decimal] = mapped_column(Numeric(2, 1), nullable=False)
    total_ratings: Mapped[int] = mapped_column(Integer, nullable=False)
    distribution: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)

    product: Mapped["Product"] = relationship(lazy="noload")

    __table_args__ = (
        UniqueConstraint("product_id"),
        CheckConstraint("average_rating BETWEEN 1.0 AND 5.0", name="average_range"),
        CheckConstraint("total_ratings >= 1", name="total_positive"),
        Index("idx_product_ratings_average", "average_rating"),
    )

    def __repr__(self) -> str:
        return (
            f"<ProductRating(product_id={self.product_id}, "
            f"average={self.average_rating}, total={self.total_ratings})>"
        )


def empty_distribution() -> dict[str, int]:
    """A zeroed 1-5 star distribution; callers increment per rating."""
    return {str(star): 0 for star in range(1, 6)}


def build_distribution(scores: list[int]) -> dict[str, int]:
    """Count ratings per star level from a list of 1-5 scores."""
    dist = empty_distribution()
    for score in scores:
        dist[str(score)] += 1
    return dist


def average_of(scores: list[int]) -> Decimal:
    """Simple average rounded to one decimal place (matches Numeric(2, 1))."""
    return (Decimal(sum(scores)) / Decimal(len(scores))).quantize(Decimal("0.1"))
