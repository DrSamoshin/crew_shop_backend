"""Idempotent dev/test seed, run by the Docker `init` service after migrations.

Loads a baseline dataset (known dev users + OAuth accounts + preferences) using the
ORM models. Dev/test only — refuses to run in stage/prod. Re-running is a no-op.

Entry point: ``python -m scripts.seed_dev``.
"""

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.configs import settings
from src.api.core.database import async_session_maker
from src.auth.enums import Provider
from src.auth.models import OAuthAccount
from src.users.models import User, UserPreferences

logger = logging.getLogger("scripts.seed_dev")

_ALLOWED_ENVS = {"dev", "test"}


@dataclass(frozen=True, slots=True)
class SeedUser:
    """A deterministic seed identity. Login matches on ``(provider, provider_id)``."""

    provider: str
    provider_id: str
    email: str
    display_name: str


# Deterministic baseline identities so tests/clients can rely on them.
# - The first is a placeholder (fake provider_id) for data presence only — not loggable.
# - The second is a real Google identity (its `sub`), so it can actually sign in locally
#   as long as the same Google client ID is used.
SEED_USERS: tuple[SeedUser, ...] = (
    SeedUser(Provider.GOOGLE.value, "seed-google-0001", "dev@crew.shop", "Dev User"),
    SeedUser(
        Provider.GOOGLE.value,
        "107265641798951898114",
        "gds.grey@gmail.com",
        "Сергей Самошин",
    ),
)


async def _seed_user(session: AsyncSession, spec: SeedUser) -> bool:
    """Create one seed user if absent. Returns True if created, False if skipped."""
    existing = await session.scalar(
        select(func.count())
        .select_from(OAuthAccount)
        .where(
            OAuthAccount.provider == spec.provider,
            OAuthAccount.provider_id == spec.provider_id,
        )
    )
    if existing:
        logger.info("seed: %s/%s already present — skipped", spec.provider, spec.provider_id)
        return False

    user = User(display_name=spec.display_name, email=spec.email)
    session.add(user)
    await session.flush()
    session.add(
        OAuthAccount(
            user_id=user.id,
            provider=spec.provider,
            provider_id=spec.provider_id,
            provider_email=spec.email,
            provider_name=spec.display_name,
        )
    )
    session.add(UserPreferences(user_id=user.id))
    await session.flush()
    logger.info("seed: created %s (%s/%s)", user.id, spec.provider, spec.provider_id)
    return True


async def seed(session: AsyncSession) -> int:
    """Create any missing baseline users (by the OAuth natural key). Returns the count created."""
    created = 0
    for spec in SEED_USERS:
        if await _seed_user(session, spec):
            created += 1
    return created


async def _run() -> None:
    async with async_session_maker() as session:
        created = await seed(session)
        await session.commit()
    logger.info("seed summary: %d user(s) created, %d skipped", created, len(SEED_USERS) - created)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if settings.env not in _ALLOWED_ENVS:
        raise SystemExit(f"seed_dev refuses to run in ENV={settings.env} (dev/test only)")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
