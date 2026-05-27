"""Tests for the dev seed script."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts import seed_dev
from src.catalog.models import (
    Category,
    Product,
    ProductCoffee,
    ProductCompatibility,
    ProductType,
)
from src.users.models import User


async def test_seed_users_is_idempotent(db_session: AsyncSession) -> None:
    created_first = await seed_dev.seed_users(db_session)
    created_again = await seed_dev.seed_users(db_session)

    assert created_first == len(seed_dev.SEED_USERS)
    assert created_again == 0

    count = await db_session.scalar(select(func.count()).select_from(User))
    assert count == len(seed_dev.SEED_USERS)


async def test_seed_catalog_is_idempotent(db_session: AsyncSession) -> None:
    created_first = await seed_dev.seed_catalog(db_session)
    created_again = await seed_dev.seed_catalog(db_session)

    expected_products = (
        len(seed_dev.SEED_COFFEES)
        + len(seed_dev.SEED_EQUIPMENT)
        + len(seed_dev.SEED_ACCESSORIES)
        + len(seed_dev.SEED_CONSUMABLES)
    )
    assert created_first == expected_products + len(seed_dev.SEED_COMPATIBILITY)
    assert created_again == 0

    assert await db_session.scalar(select(func.count()).select_from(Product)) == expected_products
    assert await db_session.scalar(select(func.count()).select_from(Category)) == len(
        seed_dev.SEED_CATEGORIES
    )
    assert await db_session.scalar(select(func.count()).select_from(ProductType)) == 4
    assert await db_session.scalar(select(func.count()).select_from(ProductCoffee)) == len(
        seed_dev.SEED_COFFEES
    )
    assert await db_session.scalar(select(func.count()).select_from(ProductCompatibility)) == len(
        seed_dev.SEED_COMPATIBILITY
    )


def test_seed_refuses_outside_dev_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed_dev.settings, "env", "prod")
    with pytest.raises(SystemExit):
        seed_dev.main()
