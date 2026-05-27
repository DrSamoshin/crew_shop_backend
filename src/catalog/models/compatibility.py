"""Compatibility links: which accessory/consumable fits which equipment (or other product)."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import UUID, CheckConstraint, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from src.catalog.models.product import Product


class ProductCompatibility(Base, TimestampMixin):
    """Directed compatibility pair: ``accessory_product_id`` fits ``compatible_product_id``."""

    __tablename__ = "product_compatibility"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    accessory_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    compatible_product_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    compatibility_notes: Mapped[str | None] = mapped_column(String(255), nullable=True)

    accessory: Mapped["Product"] = relationship(foreign_keys=[accessory_product_id], lazy="noload")
    compatible: Mapped["Product"] = relationship(
        foreign_keys=[compatible_product_id], lazy="noload"
    )

    __table_args__ = (
        UniqueConstraint("accessory_product_id", "compatible_product_id"),
        CheckConstraint(
            "accessory_product_id != compatible_product_id", name="not_self_compatible"
        ),
        # The UNIQUE constraint already indexes (accessory_product_id, compatible_product_id),
        # serving lookups by accessory; index the reverse direction explicitly.
        Index("idx_productcompat_compatible_id", "compatible_product_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<ProductCompatibility(accessory={self.accessory_product_id}, "
            f"compatible={self.compatible_product_id})>"
        )
