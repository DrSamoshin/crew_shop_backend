"""Auth orchestration: provider verification + persistence + session issuance."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import providers, sessions
from src.auth.exceptions import OAuthAccountExistsError, UserNotFoundError
from src.auth.identity import VerifiedIdentity
from src.auth.models import OAuthAccount
from src.users.service import create_user


@dataclass(frozen=True, slots=True)
class AuthResult:
    """Outcome of login/register; the endpoint turns it into the response body + cookie."""

    user_id: uuid.UUID
    access_token: str
    refresh_token: str
    is_new_user: bool


async def _get_oauth_account(
    db: AsyncSession, provider: str, provider_id: str
) -> OAuthAccount | None:
    result = await db.execute(
        select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_id == provider_id,
        )
    )
    return result.scalar_one_or_none()


async def login(db: AsyncSession, provider: str, token: str) -> AuthResult:
    """Verify the provider token and sign in an existing user."""
    identity = providers.verify_provider(provider, token)
    account = await _get_oauth_account(db, identity.provider, identity.provider_id)
    if account is None:
        raise UserNotFoundError()
    access, refresh = await sessions.create_session(db, account.user_id)
    return AuthResult(account.user_id, access, refresh, is_new_user=False)


async def register(db: AsyncSession, provider: str, token: str, name: str | None) -> AuthResult:
    """Re-verify the provider token and create user + OAuth account + preferences."""
    identity = providers.verify_provider(provider, token)
    if await _get_oauth_account(db, identity.provider, identity.provider_id) is not None:
        raise OAuthAccountExistsError()

    user = await create_user(db, _display_name(identity, name))
    db.add(
        OAuthAccount(
            user_id=user.id,
            provider=identity.provider,
            provider_id=identity.provider_id,
            provider_email=identity.email,
            provider_name=identity.name,
        )
    )
    await db.flush()
    access, refresh = await sessions.create_session(db, user.id)
    return AuthResult(user.id, access, refresh, is_new_user=True)


def _display_name(identity: VerifiedIdentity, name: str | None) -> str:
    chosen = (name or identity.name or "").strip()
    return chosen or f"User-{uuid.uuid4().hex[:8]}"
