"""Point response DTOs for the public read API."""

import uuid
from typing import Any

from pydantic import BaseModel


class PointDTO(BaseModel):
    """Customer-facing pickup point: only active ``coffeeshop`` points are exposed."""

    id: uuid.UUID
    name: str
    address: str
    hours: dict[str, Any]
    contacts: dict[str, Any]


class PointListDTO(BaseModel):
    items: list[PointDTO]
    total: int
