"""Subscription data layer: subscription + delivery info + events + per-event product + payments.

Schema follows the entity docs as the source of truth. ``Subscription`` carries only status (no
price, no selection_type — v1 is fixed-only); each ``SubscriptionEvent`` holds
``price_per_delivery``, ``scheduled_date`` and a status that gates the underlying ``Order``.
``SubscriptionDeliveryInfo`` is the v1 home of the delivery address captured at subscription
creation — the scheduler copies it into ``OrderDeliveryInfo`` when materializing an event.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import UUID as SaUUID
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin
from src.api.core.utils import sql_str_list
from src.subscriptions.enums import (
    SubscriptionEventStatus,
    SubscriptionPaymentStatus,
    SubscriptionStatus,
)

if TYPE_CHECKING:
    from src.catalog.models.product import Product
    from src.orders.models import Order
    from src.users.models import User


class Subscription(Base, TimestampMixin):
    """A user's recurring delivery subscription. Status drives the lifecycle.

    Per-event pricing (no ``price`` here); v1 is fixed-product only (no ``selection_type``).
    ``user_id`` is RESTRICT so subscriptions survive user anonymization.
    """

    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, primary_key=True, default=uuid.uuid4, server_default=sql_text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SubscriptionStatus.PENDING.value,
        server_default=sql_text(f"'{SubscriptionStatus.PENDING.value}'"),
    )

    user: Mapped["User"] = relationship(lazy="noload")
    delivery_info: Mapped["SubscriptionDeliveryInfo | None"] = relationship(
        back_populates="subscription",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    events: Mapped[list["SubscriptionEvent"]] = relationship(
        back_populates="subscription",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
        order_by="SubscriptionEvent.scheduled_date",
    )

    __table_args__ = (
        CheckConstraint(f"status IN ({sql_str_list(SubscriptionStatus)})", name="status"),
        CheckConstraint("frequency IN ('weekly', 'biweekly', 'monthly')", name="frequency"),
        Index("idx_subscriptions_status", "status"),
        Index("idx_subscriptions_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<Subscription(id={self.id}, status={self.status})>"


class SubscriptionDeliveryInfo(Base, TimestampMixin):
    """Delivery address captured at subscription creation. Mirrors ``OrderDeliveryInfo``.

    The scheduler copies these fields into ``OrderDeliveryInfo`` when materializing each event.
    """

    __tablename__ = "subscription_delivery_info"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, primary_key=True, default=uuid.uuid4, server_default=sql_text("gen_random_uuid()")
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    recipient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    subscription: Mapped["Subscription"] = relationship(
        back_populates="delivery_info", lazy="noload"
    )

    __table_args__ = (Index("idx_subscription_delivery_info_city", "city"),)

    def __repr__(self) -> str:
        return f"<SubscriptionDeliveryInfo(subscription={self.subscription_id}, city={self.city})>"


class SubscriptionEvent(Base, TimestampMixin):
    """One concrete scheduled delivery from a subscription. Status gates the underlying Order.

    Pre-created upfront (e.g. next 3-6 months); the scheduler materializes an ``Order`` on
    ``ready``. ``order_id`` is SET NULL so payment/order history survives order deletion.
    """

    __tablename__ = "subscription_events"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, primary_key=True, default=uuid.uuid4, server_default=sql_text("gen_random_uuid()")
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        SaUUID, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    scheduled_date: Mapped[date] = mapped_column(Date, nullable=False)
    price_per_delivery: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="EUR", server_default=sql_text("'EUR'")
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SubscriptionEventStatus.PENDING.value,
        server_default=sql_text(f"'{SubscriptionEventStatus.PENDING.value}'"),
    )

    subscription: Mapped["Subscription"] = relationship(back_populates="events", lazy="noload")
    product: Mapped["SubscriptionProduct | None"] = relationship(
        back_populates="event",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    payments: Mapped[list["SubscriptionPayment"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="noload",
    )
    order: Mapped["Order | None"] = relationship(lazy="noload")

    __table_args__ = (
        CheckConstraint("price_per_delivery > 0", name="price_positive"),
        CheckConstraint(f"status IN ({sql_str_list(SubscriptionEventStatus)})", name="status"),
        UniqueConstraint("subscription_id", "scheduled_date"),
        Index("idx_subscription_events_subscription_id", "subscription_id"),
        Index("idx_subscription_events_scheduled_date", "scheduled_date"),
        Index("idx_subscription_events_status", "status"),
        Index("idx_subscription_events_order_id", "order_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<SubscriptionEvent(id={self.id}, scheduled={self.scheduled_date}, "
            f"status={self.status})>"
        )


class SubscriptionProduct(Base, TimestampMixin):
    """Per-event product snapshot. One product per event (fixed-product v1)."""

    __tablename__ = "subscription_products"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, primary_key=True, default=uuid.uuid4, server_default=sql_text("gen_random_uuid()")
    )
    subscription_event_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID,
        ForeignKey("subscription_events.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, ForeignKey("products.id", ondelete="RESTRICT"), nullable=False
    )
    product_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    event: Mapped["SubscriptionEvent"] = relationship(back_populates="product", lazy="noload")
    product: Mapped["Product"] = relationship(lazy="noload")

    __table_args__ = (
        CheckConstraint("product_price > 0", name="price_positive"),
        Index("idx_subscription_products_subscription_event_id", "subscription_event_id"),
        Index("idx_subscription_products_product_id", "product_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<SubscriptionProduct(event={self.subscription_event_id}, name={self.product_name})>"
        )


class SubscriptionPayment(Base, TimestampMixin):
    """One payment attempt for a subscription event; immutable history (retry creates a new row).

    Status is independent from the event/subscription lifecycle. ``provider_transaction_id`` is the
    external id used for reconciliation; ``completed_at`` is set when the provider confirms.
    """

    __tablename__ = "subscription_payments"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, primary_key=True, default=uuid.uuid4, server_default=sql_text("gen_random_uuid()")
    )
    subscription_event_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, ForeignKey("subscription_events.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_transaction_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SubscriptionPaymentStatus.PENDING.value,
        server_default=sql_text(f"'{SubscriptionPaymentStatus.PENDING.value}'"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    event: Mapped["SubscriptionEvent"] = relationship(back_populates="payments", lazy="noload")
    user: Mapped["User"] = relationship(lazy="noload")

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(f"status IN ({sql_str_list(SubscriptionPaymentStatus)})", name="status"),
        Index("idx_subscription_payments_event_id", "subscription_event_id"),
        Index("idx_subscription_payments_user_id", "user_id"),
        Index("idx_subscription_payments_provider_txn", "provider_transaction_id"),
    )

    def __repr__(self) -> str:
        return f"<SubscriptionPayment(event={self.subscription_event_id}, status={self.status})>"
