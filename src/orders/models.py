"""Order data layer: Order plus its line items and one fulfillment info row.

Each order has exactly one fulfillment (pickup XOR delivery), enforced in the application
layer; the DB carries the generic ``status``/``order_type`` checks and the fulfillment tables.
Line items snapshot the product name and price so order history survives catalog changes.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CHAR,
    UUID,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin
from src.api.core.utils import sql_str_list
from src.orders.enums import GrindSize, OrderStatus, OrderType

if TYPE_CHECKING:
    from src.points.models import Point
    from src.users.models import User


class Order(Base, TimestampMixin):
    """A customer order. Generic fields only; fulfillment details live in the info tables.

    ``user_id`` is ``RESTRICT`` so orders survive user anonymization (audit/analytics).
    """

    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    order_type: Mapped[str] = mapped_column(String(20), nullable=False)
    total_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EUR", server_default=text("'EUR'")
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=OrderStatus.CREATED.value,
        server_default=text(f"'{OrderStatus.CREATED.value}'"),
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(lazy="noload")
    products: Mapped[list["OrderProduct"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    pickup_info: Mapped["OrderPickupInfo | None"] = relationship(
        back_populates="order",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    delivery_info: Mapped["OrderDeliveryInfo | None"] = relationship(
        back_populates="order",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )

    __table_args__ = (
        CheckConstraint("total_price > 0", name="total_price_positive"),
        CheckConstraint(f"order_type IN ({sql_str_list(OrderType)})", name="order_type"),
        CheckConstraint(f"status IN ({sql_str_list(OrderStatus)})", name="status"),
        Index("idx_orders_user_id", "user_id"),
        Index("idx_orders_status", "status"),
    )

    def __repr__(self) -> str:
        return f"<Order(id={self.id}, type={self.order_type}, status={self.status})>"


class OrderProduct(Base, TimestampMixin):
    """A line item with a name/price snapshot taken at order creation.

    ``product_id`` is ``RESTRICT``: catalog products are soft-deleted (``is_active``) rather
    than removed once ordered, so the reference and snapshot both stay valid.
    """

    __tablename__ = "order_products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    grind: Mapped[str | None] = mapped_column(String(50), nullable=True)

    order: Mapped["Order"] = relationship(back_populates="products", lazy="noload")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(f"grind IS NULL OR grind IN ({sql_str_list(GrindSize)})", name="grind"),
        Index("idx_order_products_order_id", "order_id"),
        Index("idx_order_products_product_id", "product_id"),
    )

    def __repr__(self) -> str:
        return f"<OrderProduct(id={self.id}, product={self.product_name}, qty={self.quantity})>"


class OrderPickupInfo(Base, TimestampMixin):
    """Pickup details for a pickup order (one-to-one). ``point_id`` is ``RESTRICT``.

    ``pickup_code`` is a unique 6-digit code shown to the customer; ``pickup_deadline`` is
    24h from creation; ``picked_up_at`` is set when the order is collected.
    """

    __tablename__ = "order_pickup_info"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    point_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("points.id", ondelete="RESTRICT"), nullable=False
    )
    pickup_code: Mapped[str] = mapped_column(CHAR(6), nullable=False, unique=True)
    pickup_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    picked_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order"] = relationship(back_populates="pickup_info", lazy="noload")
    point: Mapped["Point"] = relationship(lazy="noload")

    __table_args__ = (
        Index("idx_order_pickup_info_point_id", "point_id"),
        Index("idx_order_pickup_info_pickup_deadline", "pickup_deadline"),
    )

    def __repr__(self) -> str:
        return f"<OrderPickupInfo(order={self.order_id}, point={self.point_id})>"


class OrderDeliveryInfo(Base, TimestampMixin):
    """Delivery details for a delivery order (one-to-one). Address is captured immutably.

    ``shipped_at`` / ``delivered_at`` record fulfillment progress.
    """

    __tablename__ = "order_delivery_info"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    recipient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    shipped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order"] = relationship(back_populates="delivery_info", lazy="noload")

    __table_args__ = (Index("idx_order_delivery_info_city", "city"),)

    def __repr__(self) -> str:
        return f"<OrderDeliveryInfo(order={self.order_id}, city={self.city})>"
