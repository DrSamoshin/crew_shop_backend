"""Product category: a small, slowly-changing classification of the catalog."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import UUID, Boolean, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from src.catalog.models.product import Product
    from src.catalog.models.product_type import ProductType


class ProductCategory(Base, TimestampMixin):
    """Catalog category (e.g. "Specialty Coffee"). Reference data; ``is_active`` soft-hides it.

    Each category belongs to exactly one ``product_type``: the type drives which attribute
    facets the storefront renders for the category, so it is required, not derived.
    """

    __tablename__ = "product_categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    product_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("product_types.id"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    products: Mapped[list["Product"]] = relationship(back_populates="category", lazy="noload")
    product_type: Mapped["ProductType"] = relationship(lazy="noload")

    __table_args__ = (
        Index("idx_product_categories_is_active", "is_active"),
        Index("idx_product_categories_product_type_id", "product_type_id"),
    )

    def __repr__(self) -> str:
        return f"<ProductCategory(id={self.id}, name={self.name})>"
