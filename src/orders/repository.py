"""Order persistence and queries: insert, by-id detail, and the caller's paginated history.

Reads eager-load line items and the fulfillment row (pickup point joined) so the service can
map a fully populated aggregate without lazy I/O.
"""

import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.interfaces import ORMOption

from src.orders.models import Order, OrderPickupInfo


def _eager_options() -> tuple[ORMOption, ...]:
    """Eager-load line items and the (single) fulfillment row, with the pickup point joined."""
    return (
        selectinload(Order.products),
        selectinload(Order.pickup_info).joinedload(OrderPickupInfo.point),
        selectinload(Order.delivery_info),
    )


class OrderRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, order: Order) -> None:
        """Persist a new order and its children, assigning generated ids."""
        self._db.add(order)
        await self._db.flush()

    async def get(self, order_id: uuid.UUID) -> Order | None:
        stmt = (
            select(Order)
            .where(Order.id == order_id)
            .options(*_eager_options())
            .execution_options(populate_existing=True)
        )
        return (await self._db.execute(stmt)).unique().scalar_one_or_none()

    async def list_for_user(
        self,
        user_id: uuid.UUID,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[Order], int]:
        base: Select[tuple[Order]] = select(Order).where(Order.user_id == user_id)
        if status is not None:
            base = base.where(Order.status == status)
        total = await self._db.scalar(select(func.count()).select_from(base.subquery())) or 0
        stmt = (
            base.options(*_eager_options())
            .order_by(Order.created_at.desc(), Order.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self._db.execute(stmt)).unique().scalars().all()
        return list(rows), total

    async def pickup_code_exists(self, code: str) -> bool:
        found = await self._db.scalar(
            select(OrderPickupInfo.id).where(OrderPickupInfo.pickup_code == code)
        )
        return found is not None
