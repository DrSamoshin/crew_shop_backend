"""Health check schemas."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class LivenessResponse(BaseModel):
    """Liveness probe response."""

    model_config = ConfigDict(strict=True)

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    """Readiness probe response with dependency checks."""

    model_config = ConfigDict(strict=True)

    status: Literal["ok"] = "ok"
    database: Literal["ok"] = "ok"


__all__ = ["LivenessResponse", "ReadinessResponse"]
