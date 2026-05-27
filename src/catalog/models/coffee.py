"""Coffee-specific attributes (one-to-one with Product). Drives the coffee filters."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    UUID,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin
from src.catalog.enums import ProcessingMethod, RoastLevel, _quote_csv

if TYPE_CHECKING:
    from src.catalog.models.product import Product


class ProductCoffee(Base, TimestampMixin):
    """Sensory profile of a coffee product. ``id`` is also the FK to its Product row.

    ``flavor_notes`` is a multilingual JSONB object — ``keys`` holds normalized,
    machine-readable descriptors (used for filtering) plus per-language label arrays.
    """

    __tablename__ = "product_coffee"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    roast_level: Mapped[str] = mapped_column(String(20), nullable=False)
    acidity: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    body: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    sweetness: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    processing: Mapped[str] = mapped_column(String(50), nullable=False)
    altitude: Mapped[int | None] = mapped_column(Integer, nullable=True)
    flavor_notes: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="coffee", lazy="noload")

    __table_args__ = (
        CheckConstraint(f"roast_level IN ({_quote_csv(RoastLevel)})", name="roast_level"),
        CheckConstraint(f"processing IN ({_quote_csv(ProcessingMethod)})", name="processing"),
        CheckConstraint("acidity BETWEEN 1 AND 5", name="acidity_scale"),
        CheckConstraint("body BETWEEN 1 AND 5", name="body_scale"),
        CheckConstraint("sweetness BETWEEN 1 AND 5", name="sweetness_scale"),
        Index("idx_product_coffee_region", "region"),
        Index("idx_product_coffee_roast_level", "roast_level"),
        Index("idx_product_coffee_processing", "processing"),
        Index("idx_product_coffee_acidity", "acidity"),
        Index("idx_product_coffee_body", "body"),
        Index("idx_product_coffee_sweetness", "sweetness"),
        Index("idx_product_coffee_altitude", "altitude"),
        # GIN over the normalized flavor keys for containment filtering (`@>`).
        Index(
            "idx_product_coffee_flavor_keys",
            text("(flavor_notes -> 'keys')"),
            postgresql_using="gin",
        ),
    )

    def __repr__(self) -> str:
        return f"<ProductCoffee(id={self.id}, region={self.region}, roast={self.roast_level})>"
