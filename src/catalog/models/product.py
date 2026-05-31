"""Base product table. Type-specific attributes live in one-to-one subtype tables."""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    UUID,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from src.catalog.models.accessory import ProductAccessories
    from src.catalog.models.coffee import ProductCoffee
    from src.catalog.models.consumable import ProductConsumables
    from src.catalog.models.equipment import ProductEquipment
    from src.catalog.models.product_category import ProductCategory
    from src.catalog.models.product_type import ProductType


class Product(Base, TimestampMixin):
    """A catalog product. ``product_type_id`` selects which subtype table holds its attributes.

    ``price`` is the current price (EUR); order lines snapshot it. ``is_active`` soft-deletes
    discontinued products so existing orders keep their reference.
    """

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    product_category_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("product_categories.id"), nullable=False
    )
    product_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("product_types.id"), nullable=False
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EUR", server_default=text("'EUR'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    category: Mapped["ProductCategory"] = relationship(back_populates="products", lazy="noload")
    product_type: Mapped["ProductType"] = relationship(back_populates="products", lazy="noload")

    coffee: Mapped["ProductCoffee | None"] = relationship(
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    equipment: Mapped["ProductEquipment | None"] = relationship(
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    accessory: Mapped["ProductAccessories | None"] = relationship(
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    consumable: Mapped["ProductConsumables | None"] = relationship(
        back_populates="product",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )

    __table_args__ = (
        CheckConstraint("price > 0", name="price_positive"),
        Index("idx_products_product_category_id", "product_category_id"),
        Index("idx_products_product_type_id", "product_type_id"),
        Index("idx_products_is_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name={self.name})>"
