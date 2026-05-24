"""Health check endpoints (liveness and readiness probes)."""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.api.v1.schemas.health import LivenessResponse, ReadinessResponse

router = APIRouter(prefix="/health", tags=["system"])


@router.get(
    "/live",
    response_model=LivenessResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
)
async def liveness() -> LivenessResponse:
    """Return ok if the service process is running."""
    return LivenessResponse()


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    status_code=status.HTTP_200_OK,
    summary="Readiness probe",
)
async def readiness(db: Annotated[AsyncSession, Depends(get_db)]) -> ReadinessResponse:
    """Check database connectivity before reporting ready."""
    await db.execute(text("SELECT 1"))
    return ReadinessResponse()
