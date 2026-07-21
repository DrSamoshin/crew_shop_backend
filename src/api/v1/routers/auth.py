"""Auth endpoints: session / refresh / logout.

crew_shop is not an identity provider. The browser signs in at crew_auth's hosted login
and comes back to the SPA with a one-time code; the SPA posts it here and crew_shop
redeems it server-to-server. There is no ``/register``: an identity crew_auth has never
seen simply becomes a new user.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.api.v1.schemas.auth import (
    RefreshRequest,
    SessionRequest,
    SessionResponse,
    TokenResponse,
)
from src.auth import crew_auth, service
from src.auth.dependencies import require_auth
from src.users import service as users_service
from src.users.models import User
from src.users.schemas import to_profile_dto

router = APIRouter(prefix="/auth", tags=["auth"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post(
    "/session",
    response_model=SessionResponse,
    summary="Redeem a crew_auth login code for a session",
)
async def create_session(payload: SessionRequest, db: DbDep) -> SessionResponse:
    result = await service.sign_in(db, payload.code)
    profile = await users_service.get_me(db, result.user.id)
    return SessionResponse(
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_in=result.expires_in,
        is_new_user=result.is_new_user,
        user=to_profile_dto(profile),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Exchange a refresh token for a rotated pair",
)
async def refresh(payload: RefreshRequest) -> TokenResponse:
    """Thin pass-through to crew_auth.

    It exists only because crew_auth wires no CORS and the browser therefore cannot call
    it directly. crew_shop holds no refresh state and must not interpret the token.
    """
    tokens = await crew_auth.refresh_tokens(payload.refresh_token)
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="End the client's session",
)
async def logout(user: Annotated[User, Depends(require_auth)]) -> None:
    """Tell the client to discard its tokens. There is nothing server-side to revoke.

    crew_auth's ``/logout`` kills only its own SSO cookie and deliberately does not
    revoke refresh tokens held by services, and it exposes no revoke endpoint — so the
    refresh token stays valid for its 30 days. A full sign-out additionally requires
    navigating the browser to crew_auth's ``/logout``. A local denylist is deliberately
    not used: it would reintroduce the per-request session read this design removed.
    """
    return None
