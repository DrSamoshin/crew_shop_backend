"""Consumable-specific attributes (one-to-one with Product): filters, pods, cleaning, ..."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import UUID, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin
from src.catalog.enums import ConsumableType, _quote_csv

if TYPE_CHECKING:
    from src.catalog.models.product import Product


class ProductConsumables(Base, TimestampMixin):
    """Attributes of a consumable product. ``id`` is the FK to Product.

    ``quantity_per_pack`` + ``unit_description`` define what one purchasable unit contains.
    """

    __tablename__ = "product_consumables"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    consumable_type: Mapped[str] = mapped_column(String(50), nullable=False)
    quantity_per_pack: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_description: Mapped[str] = mapped_column(String(50), nullable=False)
    material: Mapped[str | None] = mapped_column(String(100), nullable=True)
    other_options: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    expiry_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_conditions: Mapped[str | None] = mapped_column(String(255), nullable=True)

    product: Mapped["Product"] = relationship(back_populates="consumable", lazy="noload")

    __table_args__ = (
        CheckConstraint(
            f"consumable_type IN ({_quote_csv(ConsumableType)})", name="consumable_type"
        ),
        CheckConstraint("quantity_per_pack > 0", name="quantity_positive"),
        CheckConstraint("expiry_months IS NULL OR expiry_months > 0", name="expiry_positive"),
    )

    def __repr__(self) -> str:
        return f"<ProductConsumables(id={self.id}, type={self.consumable_type})>"
