"""Auth endpoints: login / register / token refresh / logout.

Tokens are delivered in the response body (no cookies). The access token is sent
as a bearer header by the client; the refresh token is held by the client and
posted back to ``/token/refresh``. Sessions are still server-side, so logout and
refresh rotation (with reuse detection) enforce immediate revocation.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.configs import settings
from src.api.core.database import get_db
from src.api.v1.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse
from src.auth import service, sessions, tokens
from src.auth.dependencies import require_session
from src.auth.models import Session

router = APIRouter(prefix="/auth", tags=["auth"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _token_response(result: service.AuthResult) -> TokenResponse:
    return TokenResponse(
        user_id=result.user_id,
        access_token=result.access_token,
        refresh_token=result.refresh_token,
        expires_in=settings.access_token_ttl,
        is_new_user=result.is_new_user,
    )


@router.post("/login", response_model=TokenResponse, summary="Sign in with a provider token")
async def login(payload: LoginRequest, db: DbDep) -> TokenResponse:
    result = await service.login(db, payload.provider, payload.token)
    return _token_response(result)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account from a verified provider identity",
)
async def register(payload: RegisterRequest, db: DbDep) -> TokenResponse:
    result = await service.register(db, payload.provider, payload.token, payload.name)
    return _token_response(result)


@router.post(
    "/token/refresh",
    response_model=TokenResponse,
    summary="Exchange a refresh token for a new access token",
)
async def refresh_token(payload: RefreshRequest, db: DbDep) -> TokenResponse:
    access, new_refresh = await sessions.refresh(db, payload.refresh_token)
    claims = tokens.decode(access, expected_type=tokens.TOKEN_TYPE_ACCESS)
    return TokenResponse(
        user_id=claims["sub"],
        access_token=access,
        refresh_token=new_refresh,
        expires_in=settings.access_token_ttl,
        is_new_user=False,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current session",
)
async def logout(
    db: DbDep,
    session: Annotated[Session, Depends(require_session)],
) -> None:
    await sessions.logout(db, session.id)
