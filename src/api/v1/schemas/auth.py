"""Auth request/response schemas."""

import uuid
from typing import Literal

from pydantic import BaseModel, Field

# `provider` is a plain string (not the Provider enum) so an unknown value reaches
# verify_provider and surfaces as AUTH_INVALID_PROVIDER (400), not a 422 validation error.


class LoginRequest(BaseModel):
    """Sign in with a provider ID token."""

    provider: str
    token: str = Field(min_length=1)


class RegisterRequest(BaseModel):
    """Create an account from a verified provider identity.

    ``name`` is an optional display-name hint (e.g. Apple's first-auth name); the
    backend re-verifies ``token`` and never trusts client-sent identity.
    """

    provider: str
    token: str = Field(min_length=1)
    name: str | None = None


class TokenResponse(BaseModel):
    """Token response body. The refresh token is delivered via an httpOnly cookie."""

    user_id: uuid.UUID
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    is_new_user: bool


__all__ = ["LoginRequest", "RegisterRequest", "TokenResponse"]
