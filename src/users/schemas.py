"""User account request and response DTOs.

Updates are partial: only fields present in the request body are applied (tracked via
``model_fields_set``), so ``email`` can be explicitly set to ``null`` while an omitted field is
left untouched.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from src.users.models import User, UserPreferences


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


def to_preferences_dto(prefs: "UserPreferences") -> PreferencesDTO:
    return PreferencesDTO(language=prefs.language, timezone=prefs.timezone)


def to_profile_dto(user: "User") -> UserProfileDTO:
    """Build the profile DTO. ``user.preferences`` must already be loaded."""
    return UserProfileDTO(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        preferences=to_preferences_dto(user.preferences),
    )
