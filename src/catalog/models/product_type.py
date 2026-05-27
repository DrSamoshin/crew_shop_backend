"""Product type: the four top-level kinds, each backed by its own attribute table."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import UUID, Boolean, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from src.catalog.models.product import Product


class ProductType(Base, TimestampMixin):
    """Product type (coffee, equipment, accessories, consumables). Reference data."""

    __tablename__ = "product_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    products: Mapped[list["Product"]] = relationship(back_populates="product_type", lazy="noload")

    def __repr__(self) -> str:
        return f"<ProductType(id={self.id}, name={self.name})>"
