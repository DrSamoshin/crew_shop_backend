"""Tests for the dev seed script."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts import seed_dev
from src.users.models import User


async def test_seed_is_idempotent(db_session: AsyncSession) -> None:
    created_first = await seed_dev.seed(db_session)
    created_again = await seed_dev.seed(db_session)

    assert created_first == len(seed_dev.SEED_USERS)
    assert created_again == 0

    count = await db_session.scalar(select(func.count()).select_from(User))
    assert count == len(seed_dev.SEED_USERS)


def test_seed_refuses_outside_dev_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_dev.settings, "env", "prod")
    with pytest.raises(SystemExit):
        seed_dev.main()
