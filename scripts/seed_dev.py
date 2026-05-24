"""Idempotent dev/test seed, run by the Docker `init` service after migrations.

Loads a baseline dataset (a known dev user + OAuth account + preferences) using the
ORM models. Dev/test only — refuses to run in stage/prod. Re-running is a no-op.

Entry point: ``python -m scripts.seed_dev``.
"""

import asyncio
import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.configs import settings
from src.api.core.database import async_session_maker
from src.auth.enums import Provider
from src.auth.models import OAuthAccount
from src.users.models import User, UserPreferences

logger = logging.getLogger("scripts.seed_dev")

_ALLOWED_ENVS = {"dev", "test"}

# Deterministic baseline identity so tests/clients can rely on it.
SEED_PROVIDER = Provider.GOOGLE.value
SEED_PROVIDER_ID = "seed-google-0001"
SEED_EMAIL = "dev@crew.shop"
SEED_DISPLAY_NAME = "Dev User"


async def seed(session: AsyncSession) -> bool:
    """Create the baseline dev user if absent. Returns True if created, False if skipped."""
    existing = await session.scalar(
        select(func.count())
        .select_from(OAuthAccount)
        .where(
            OAuthAccount.provider == SEED_PROVIDER,
            OAuthAccount.provider_id == SEED_PROVIDER_ID,
        )
    )
    if existing:
        logger.info("seed: dev user already present — skipped")
        return False

    user = User(display_name=SEED_DISPLAY_NAME, email=SEED_EMAIL)
    session.add(user)
    await session.flush()
    session.add(
        OAuthAccount(
            user_id=user.id,
            provider=SEED_PROVIDER,
            provider_id=SEED_PROVIDER_ID,
            provider_email=SEED_EMAIL,
            provider_name=SEED_DISPLAY_NAME,
        )
    )
    session.add(UserPreferences(user_id=user.id))
    await session.flush()
    logger.info("seed: created dev user %s (%s/%s)", user.id, SEED_PROVIDER, SEED_PROVIDER_ID)
    return True


async def _run() -> None:
    async with async_session_maker() as session:
        created = await seed(session)
        await session.commit()
    logger.info("seed summary: dev_user=%s", "created" if created else "skipped")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if settings.env not in _ALLOWED_ENVS:
        raise SystemExit(f"seed_dev refuses to run in ENV={settings.env} (dev/test only)")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
