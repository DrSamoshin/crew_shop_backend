"""Admin write request DTOs for the points API; the admin detail response carries every field."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.points.enums import PointType


class _PointWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1)
    type: PointType
    hours: dict[str, Any]
    contacts: dict[str, Any]
    is_active: bool = True


class PointCreate(_PointWrite):
    """All fields required; defaults to ``is_active=True``."""


class PointUpdate(_PointWrite):
    """Replace-style update (PUT); all fields are required so updates are deterministic."""


class PointAdminDTO(BaseModel):
    """Full point detail returned to the admin caller (includes ``is_active`` and timestamps)."""

    id: uuid.UUID
    name: str
    address: str
    type: str
    hours: dict[str, Any]
    contacts: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime
