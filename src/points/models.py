"""Point: a business location. Order pickup references a ``coffeeshop`` point."""

import uuid
from typing import Any

from sqlalchemy import (
    UUID,
    Boolean,
    CheckConstraint,
    Index,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.api.core.database import Base, TimestampMixin
from src.api.core.utils import sql_str_list
from src.points.enums import PointType


class Point(Base, TimestampMixin):
    """A physical business location (coffeeshop, warehouse or roastery).

    Pickup orders reference a ``coffeeshop`` point; ``is_active`` soft-disables a location
    without breaking existing orders (the pickup FK is ``RESTRICT``).
    """

    __tablename__ = "points"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    hours: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    contacts: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    __table_args__ = (
        CheckConstraint(f"type IN ({sql_str_list(PointType)})", name="type"),
        Index("idx_points_type", "type"),
        Index("idx_points_is_active", "is_active"),
        Index("idx_points_name", "name"),
    )

    def __repr__(self) -> str:
        return f"<Point(id={self.id}, name={self.name}, type={self.type})>"
