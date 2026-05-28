"""Payment domain models: ``OrderPayment`` (per-attempt immutable history) and
``PaymentMethod`` (a user's saved card with the provider's customer + token).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import UUID as SaUUID
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy import text as sql_text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.core.database import Base, TimestampMixin
from src.api.core.utils import sql_str_list
from src.payments.enums import PaymentStatus

if TYPE_CHECKING:
    from src.orders.models import Order
    from src.users.models import User


class OrderPayment(Base, TimestampMixin):
    """A single payment attempt for an order.

    ``order_id`` and ``user_id`` are RESTRICT so payment history survives order/user
    anonymization. ``provider_transaction_id`` is the external id used for reconciliation;
    ``completed_at`` is set when the provider confirms the transaction.
    """

    __tablename__ = "order_payments"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, primary_key=True, default=uuid.uuid4, server_default=sql_text("gen_random_uuid()")
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False
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
        default=PaymentStatus.PENDING.value,
        server_default=sql_text(f"'{PaymentStatus.PENDING.value}'"),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped["Order"] = relationship(lazy="noload")
    user: Mapped["User"] = relationship(lazy="noload")

    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint(f"status IN ({sql_str_list(PaymentStatus)})", name="status"),
        Index("idx_order_payments_order_id", "order_id"),
        Index("idx_order_payments_user_id", "user_id"),
        Index("idx_order_payments_provider_txn", "provider_transaction_id"),
    )

    def __repr__(self) -> str:
        return f"<OrderPayment(id={self.id}, order={self.order_id}, status={self.status})>"


class PaymentMethod(Base, TimestampMixin):
    """A user's saved payment method (one row per card).

    ``provider_customer_id`` + ``provider_method_token`` are opaque, handed back to the
    ``PaymentProvider`` for off-session charges. Display fields (brand / last4 / exp) are
    captured at save time so the Account UI renders the card without a provider round-trip.
    ``is_default`` marks the card the subscription wizard picks unless explicitly overridden;
    the service maintains the invariant that at most one method per user is default.
    """

    __tablename__ = "payment_methods"

    id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, primary_key=True, default=uuid.uuid4, server_default=sql_text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        SaUUID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_customer_id: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_method_token: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str] = mapped_column(String(30), nullable=False)
    last4: Mapped[str] = mapped_column(String(4), nullable=False)
    exp_month: Mapped[int] = mapped_column(Integer, nullable=False)
    exp_year: Mapped[int] = mapped_column(Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=sql_text("false")
    )

    user: Mapped["User"] = relationship(lazy="noload")

    __table_args__ = (
        UniqueConstraint("provider", "provider_method_token", name="provider_token"),
        CheckConstraint("exp_month BETWEEN 1 AND 12", name="exp_month_range"),
        Index("idx_payment_methods_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<PaymentMethod(id={self.id}, user={self.user_id}, {self.brand} ****{self.last4})>"
