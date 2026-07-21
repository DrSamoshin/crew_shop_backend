"""Auth orchestration: redeem a crew_auth login code and anchor it to a shop account."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import crew_auth
from src.users.models import User
from src.users.service import create_user


@dataclass(frozen=True, slots=True)
class SignInResult:
    """Outcome of a sign-in; the endpoint turns it into the response body."""

    user: User
    access_token: str
    refresh_token: str
    expires_in: int
    is_new_user: bool


def _initial_display_name(auth_user_id: uuid.UUID) -> str:
    """Placeholder name for a brand-new account.

    crew_auth holds no name and has no plan to, so the client prompts for one on first
    sign-in and saves it through ``PUT /v1/users/me``.
    """
    return f"User-{auth_user_id.hex[:8]}"


async def sign_in(db: AsyncSession, code: str) -> SignInResult:
    """Exchange a one-time login code and return the caller's account.

    There is no separate registration: an identity crew_auth has never seen simply
    becomes a new user, so this upserts on ``auth_user_id`` and reports ``is_new_user``
    for the client's first-sign-in prompt.
    """
    tokens = await crew_auth.exchange_code(code)

    user = await db.scalar(select(User).where(User.auth_user_id == tokens.user_id))
    is_new = user is None
    if user is None:
        user = await create_user(
            db, _initial_display_name(tokens.user_id), auth_user_id=tokens.user_id
        )

    return SignInResult(
        user=user,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
        is_new_user=is_new,
    )
