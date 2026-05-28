"""Admin (S2S-gated) points API, separate from the public read API.

Trusted only for the crew_admin backend: every request carries the per-environment service
token, and the acting operator/role is recorded for audit. Validation is authoritative.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.points.admin.dependencies import ServiceCaller, audit, require_service_caller
from src.points.admin.schemas import PointAdminDTO, PointCreate, PointUpdate
from src.points.admin.service import AdminPointsService

router = APIRouter(prefix="/admin/points", tags=["points-admin"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
CallerDep = Annotated[ServiceCaller, Depends(require_service_caller)]


@router.post(
    "",
    response_model=PointAdminDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create a pickup point",
)
async def create_point(payload: PointCreate, db: DbDep, caller: CallerDep) -> PointAdminDTO:
    point = await AdminPointsService(db).create(payload)
    audit(caller, "create", f"point:{point.id}")
    return point


@router.put(
    "/{point_id}",
    response_model=PointAdminDTO,
    summary="Replace a pickup point",
)
async def update_point(
    point_id: uuid.UUID, payload: PointUpdate, db: DbDep, caller: CallerDep
) -> PointAdminDTO:
    point = await AdminPointsService(db).update(point_id, payload)
    audit(caller, "update", f"point:{point_id}")
    return point


@router.delete(
    "/{point_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a pickup point (soft if referenced; hard otherwise)",
)
async def delete_point(
    point_id: uuid.UUID,
    db: DbDep,
    caller: CallerDep,
    mode: Annotated[Literal["auto", "hard"], Query()] = "auto",
) -> None:
    await AdminPointsService(db).delete(point_id, mode=mode)
    audit(caller, f"delete:{mode}", f"point:{point_id}")
