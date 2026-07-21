"""Personal-account endpoints for the signed-in user, all scoped to ``/v1/users/me``.

Every endpoint requires a bearer access token (the caller acts only on their own account).
Errors flow through the shared AppException envelope.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.auth.dependencies import require_auth
from src.users import service
from src.users.models import User
from src.users.schemas import (
    PreferencesDTO,
    UpdatePreferencesRequest,
    UpdateProfileRequest,
    UserProfileDTO,
    to_preferences_dto,
    to_profile_dto,
)

router = APIRouter(prefix="/users", tags=["users"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(require_auth)]


@router.get("/me", response_model=UserProfileDTO, summary="Get the caller's account")
async def get_me(db: DbDep, user: UserDep) -> UserProfileDTO:
    return to_profile_dto(await service.get_me(db, user.id))


@router.put("/me", response_model=UserProfileDTO, summary="Update the caller's profile")
async def update_me(payload: UpdateProfileRequest, db: DbDep, user: UserDep) -> UserProfileDTO:
    return to_profile_dto(await service.update_profile(db, user.id, payload))


@router.put(
    "/me/preferences", response_model=PreferencesDTO, summary="Update the caller's preferences"
)
async def update_preferences(
    payload: UpdatePreferencesRequest, db: DbDep, user: UserDep
) -> PreferencesDTO:
    return to_preferences_dto(await service.update_preferences(db, user.id, payload))


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT, summary="Delete the caller's account")
async def delete_me(
    db: DbDep,
    user: UserDep,
    mode: Annotated[Literal["hard", "soft"], Query()] = "hard",
) -> None:
    await service.delete_account(db, user.id, mode)
