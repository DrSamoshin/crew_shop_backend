"""Point response DTOs for the public read API.

``hours`` and ``contacts`` are typed for the web (per-day open/close, structured contact
fields). Both validation models tolerate legacy / extra keys via ``extra="ignore"`` so older
JSONB shapes don't break the response.
"""

import uuid

from pydantic import BaseModel, ConfigDict


class DailyHoursDTO(BaseModel):
    """One day's hours: ``HH:MM`` strings. Either field may be missing for closed days."""

    model_config = ConfigDict(extra="ignore")

    open: str | None = None
    close: str | None = None


class WeeklyHoursDTO(BaseModel):
    """Weekly schedule, day-keyed. Missing or null days mean closed."""

    model_config = ConfigDict(extra="ignore")

    monday: DailyHoursDTO | None = None
    tuesday: DailyHoursDTO | None = None
    wednesday: DailyHoursDTO | None = None
    thursday: DailyHoursDTO | None = None
    friday: DailyHoursDTO | None = None
    saturday: DailyHoursDTO | None = None
    sunday: DailyHoursDTO | None = None


class PointContactsDTO(BaseModel):
    """Structured contact info for a point."""

    model_config = ConfigDict(extra="ignore")

    phone: str | None = None
    email: str | None = None
    manager: str | None = None
    manager_phone: str | None = None


class PointDTO(BaseModel):
    """Customer-facing pickup point: only active ``coffeeshop`` points are exposed."""

    id: uuid.UUID
    name: str
    address: str
    hours: WeeklyHoursDTO
    contacts: PointContactsDTO


class PointListDTO(BaseModel):
    items: list[PointDTO]
    total: int
