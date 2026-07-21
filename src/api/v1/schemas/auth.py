"""Auth request/response schemas.

crew_shop issues no tokens of its own: every token in these bodies is crew_auth's,
passed through. The access token is sent back as a bearer header by the client; the
refresh token is held by the client and posted to ``/v1/auth/refresh``.
"""

from typing import Literal

from pydantic import BaseModel, Field

from src.users.schemas import UserProfileDTO


class SessionRequest(BaseModel):
    """Redeem the one-time code crew_auth appended to the callback URL."""

    code: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    """Exchange a refresh token for a rotated pair. The presented token is revoked."""

    refresh_token: str = Field(min_length=1)


class SessionResponse(BaseModel):
    """A signed-in session: crew_auth's tokens plus the caller's shop profile.

    ``is_new_user`` tells the client to prompt for a display name — crew_auth holds no
    name, so a fresh account starts with a generated placeholder.
    """

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    is_new_user: bool
    user: UserProfileDTO


class TokenResponse(BaseModel):
    """A rotated token pair. Carries no profile — the caller already has one."""

    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


__all__ = ["RefreshRequest", "SessionRequest", "SessionResponse", "TokenResponse"]
