"""Points service: list active coffeeshop points and detail (customer-facing).

Warehouses and roasteries are internal and never exposed by this layer; an inactive or
non-coffeeshop point looks the same as a missing one to a public caller (``POINT_NOT_FOUND``).
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.points.enums import PointType
from src.points.exceptions import PointNotFoundError
from src.points.models import Point
from src.points.schemas import PointDTO, PointListDTO


def _to_dto(point: Point) -> PointDTO:
    return PointDTO(
        id=point.id,
        name=point.name,
        address=point.address,
        hours=point.hours,
        contacts=point.contacts,
    )


async def list_active_coffeeshops(db: AsyncSession) -> PointListDTO:
    """Active ``coffeeshop`` points, ordered by name for deterministic listings."""
    rows = (
        await db.scalars(
            select(Point)
            .where(Point.type == PointType.COFFEESHOP.value, Point.is_active.is_(True))
            .order_by(Point.name.asc(), Point.id.asc())
        )
    ).all()
    return PointListDTO(items=[_to_dto(p) for p in rows], total=len(rows))


async def get_point(db: AsyncSession, point_id: uuid.UUID) -> PointDTO:
    """Detail for an active coffeeshop point; raises ``POINT_NOT_FOUND`` otherwise."""
    point = await db.scalar(
        select(Point).where(
            Point.id == point_id,
            Point.type == PointType.COFFEESHOP.value,
            Point.is_active.is_(True),
        )
    )
    if point is None:
        raise PointNotFoundError(str(point_id))
    return _to_dto(point)
