"""Equipment-specific attributes (one-to-one with Product): machines, grinders, brewers, ..."""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import UUID, CheckConstraint, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin
from src.catalog.enums import EquipmentType, _quote_csv

if TYPE_CHECKING:
    from src.catalog.models.product import Product


class ProductEquipment(Base, TimestampMixin):
    """Physical/technical attributes of an equipment product. ``id`` is the FK to Product."""

    __tablename__ = "product_equipment"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
    )
    equipment_type: Mapped[str] = mapped_column(String(50), nullable=False)
    power_watts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warranty_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    depth_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    material: Mapped[str | None] = mapped_column(String(100), nullable=True)
    other_options: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="equipment", lazy="noload")

    __table_args__ = (
        CheckConstraint(f"equipment_type IN ({_quote_csv(EquipmentType)})", name="equipment_type"),
        CheckConstraint("power_watts IS NULL OR power_watts > 0", name="power_positive"),
        CheckConstraint(
            "warranty_months IS NULL OR warranty_months >= 0", name="warranty_non_negative"
        ),
        CheckConstraint("width_cm IS NULL OR width_cm > 0", name="width_positive"),
        CheckConstraint("height_cm IS NULL OR height_cm > 0", name="height_positive"),
        CheckConstraint("depth_cm IS NULL OR depth_cm > 0", name="depth_positive"),
    )

    def __repr__(self) -> str:
        return f"<ProductEquipment(id={self.id}, type={self.equipment_type})>"
