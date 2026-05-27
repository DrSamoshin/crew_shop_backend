"""Product category: a small, slowly-changing classification of the catalog."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import UUID, Boolean, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin

if TYPE_CHECKING:
    from src.catalog.models.product import Product


class Category(Base, TimestampMixin):
    """Catalog category (e.g. "Specialty Coffee"). Reference data; ``is_active`` soft-hides it."""

    __tablename__ = "categories"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    products: Mapped[list["Product"]] = relationship(back_populates="category", lazy="noload")

    __table_args__ = (Index("idx_categories_is_active", "is_active"),)

    def __repr__(self) -> str:
        return f"<Category(id={self.id}, name={self.name})>"
