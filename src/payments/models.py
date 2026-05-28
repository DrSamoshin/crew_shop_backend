"""``OrderPayment``: provider-agnostic payment record for an order (EUR, immutable history).

Each payment attempt is its own row; failed and refunded are terminal. Payment status is
independent from the parent ``Order`` lifecycle (a failed payment does not move the order).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import UUID as SaUUID
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
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
