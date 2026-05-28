"""Admin write operations for points. Server-side validation is authoritative.

Delete picks soft vs hard automatically based on whether the point is referenced by an
``OrderPickupInfo`` row: referenced → ``is_active = false`` (soft); unreferenced → physical
delete. ``mode=hard`` may be passed explicitly to force a hard delete and surface
``POINT_IN_USE`` (409) when the point is still referenced.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.orders.models import OrderPickupInfo
from src.points.admin.schemas import PointAdminDTO, PointCreate, PointUpdate
from src.points.exceptions import PointInUseError, PointNotFoundError
from src.points.models import Point


def _to_dto(point: Point) -> PointAdminDTO:
    return PointAdminDTO(
        id=point.id,
        name=point.name,
        address=point.address,
        type=point.type,
        hours=point.hours,
        contacts=point.contacts,
        is_active=point.is_active,
        created_at=point.created_at,
        updated_at=point.updated_at,
    )


class AdminPointsService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _require(self, point_id: uuid.UUID) -> Point:
        point = await self._db.get(Point, point_id)
        if point is None:
            raise PointNotFoundError(str(point_id))
        return point

    async def _is_referenced(self, point_id: uuid.UUID) -> bool:
        found = await self._db.scalar(
            select(OrderPickupInfo.id).where(OrderPickupInfo.point_id == point_id).limit(1)
        )
        return found is not None

    async def create(self, data: PointCreate) -> PointAdminDTO:
        point = Point(
            name=data.name,
            address=data.address,
            type=data.type.value,
            hours=data.hours,
            contacts=data.contacts,
            is_active=data.is_active,
        )
        self._db.add(point)
        await self._db.flush()
        return _to_dto(point)

    async def update(self, point_id: uuid.UUID, data: PointUpdate) -> PointAdminDTO:
        point = await self._require(point_id)
        point.name = data.name
        point.address = data.address
        point.type = data.type.value
        point.hours = data.hours
        point.contacts = data.contacts
        point.is_active = data.is_active
        await self._db.flush()
        # Refresh so the onupdate-driven ``updated_at`` is pulled into the instance and the
        # response builder doesn't trigger a sync-lazy load in an async request.
        await self._db.refresh(point)
        return _to_dto(point)

    async def delete(self, point_id: uuid.UUID, *, mode: str = "auto") -> None:
        """``auto`` (default): soft if referenced, hard otherwise. ``hard``: 409 if referenced."""
        point = await self._require(point_id)
        referenced = await self._is_referenced(point_id)
        if mode == "hard" and referenced:
            raise PointInUseError(str(point_id))
        if referenced:
            point.is_active = False
            await self._db.flush()
            return
        await self._db.delete(point)
        await self._db.flush()
