"""Public pickup-points endpoints: list active coffeeshops and point detail."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.points import service
from src.points.schemas import PointDTO, PointListDTO

router = APIRouter(prefix="/points", tags=["points"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=PointListDTO, summary="List active coffeeshop pickup points")
async def list_points(db: DbDep) -> PointListDTO:
    return await service.list_active_coffeeshops(db)


@router.get("/{point_id}", response_model=PointDTO, summary="Get a pickup point's detail")
async def get_point(point_id: uuid.UUID, db: DbDep) -> PointDTO:
    return await service.get_point(db, point_id)
