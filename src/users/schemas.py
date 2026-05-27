"""User account request and response DTOs.

Updates are partial: only fields present in the request body are applied (tracked via
``model_fields_set``), so ``email`` can be explicitly set to ``null`` while an omitted field is
left untouched.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel


class UpdateProfileRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None


class UpdatePreferencesRequest(BaseModel):
    language: str | None = None
    timezone: str | None = None


class PreferencesDTO(BaseModel):
    language: str
    timezone: str


class UserProfileDTO(BaseModel):
    id: uuid.UUID
    email: str | None
    display_name: str
    is_active: bool
    created_at: datetime
    preferences: PreferencesDTO
