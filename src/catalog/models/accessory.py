"""Accessory-specific attributes (one-to-one with Product): filters, tampers, pitchers, ..."""

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import UUID, CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin
from src.catalog.enums import AccessoryType, _quote_csv

if TYPE_CHECKING:
    from src.catalog.models.product import Product


class ProductAccessories(Base, TimestampMixin):
    """Attributes of an accessory product. ``id`` is the FK to Product; ``material`` is required."""

    __tablename__ = "product_accessories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    accessory_type: Mapped[str] = mapped_column(String(50), nullable=False)
    material: Mapped[str] = mapped_column(String(100), nullable=False)
    other_options: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="accessory", lazy="noload")

    __table_args__ = (
        CheckConstraint(f"accessory_type IN ({_quote_csv(AccessoryType)})", name="accessory_type"),
    )

    def __repr__(self) -> str:
        return f"<ProductAccessories(id={self.id}, type={self.accessory_type})>"
