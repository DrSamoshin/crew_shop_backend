"""Auth endpoints: login / register / token refresh / logout."""

from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.configs import settings
from src.api.core.database import get_db
from src.api.v1.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from src.auth import service, sessions, tokens
from src.auth.cookies import (
    REFRESH_COOKIE,
    clear_auth_cookies,
    require_csrf,
    set_auth_cookies,
)
from src.auth.dependencies import require_session
from src.auth.exceptions import InvalidTokenError
from src.auth.models import Session

router = APIRouter(prefix="/auth", tags=["auth"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _token_response(result: service.AuthResult) -> TokenResponse:
    return TokenResponse(
        user_id=result.user_id,
        access_token=result.access_token,
        expires_in=settings.access_token_ttl,
        is_new_user=result.is_new_user,
    )


@router.post("/login", response_model=TokenResponse, summary="Sign in with a provider token")
async def login(payload: LoginRequest, response: Response, db: DbDep) -> TokenResponse:
    result = await service.login(db, payload.provider, payload.token)
    set_auth_cookies(response, result.refresh_token)
    return _token_response(result)


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account from a verified provider identity",
)
async def register(payload: RegisterRequest, response: Response, db: DbDep) -> TokenResponse:
    result = await service.register(db, payload.provider, payload.token, payload.name)
    set_auth_cookies(response, result.refresh_token)
    return _token_response(result)


@router.post(
    "/token/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(require_csrf)],
    summary="Exchange the refresh cookie for a new access token",
)
async def refresh_token(
    response: Response,
    db: DbDep,
    refresh_token: Annotated[str | None, Cookie(alias=REFRESH_COOKIE)] = None,
) -> TokenResponse:
    if not refresh_token:
        raise InvalidTokenError("Missing refresh token")
    access, new_refresh = await sessions.refresh(db, refresh_token)
    set_auth_cookies(response, new_refresh)
    claims = tokens.decode(access, expected_type=tokens.TOKEN_TYPE_ACCESS)
    return TokenResponse(
        user_id=claims["sub"],
        access_token=access,
        expires_in=settings.access_token_ttl,
        is_new_user=False,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_csrf)],
    summary="Revoke the current session",
)
async def logout(
    response: Response,
    db: DbDep,
    session: Annotated[Session, Depends(require_session)],
) -> None:
    await sessions.logout(db, session.id)
    clear_auth_cookies(response)
