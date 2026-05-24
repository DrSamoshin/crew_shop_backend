"""Integration test harness: a session bound to a real PostgreSQL test database.

Runs against the Docker Postgres (see docker-compose.yml). Uses a dedicated
`crew_shop_test` database so it never touches dev data, recreating the schema
from the models before each test for isolation.
"""

from collections.abc import AsyncGenerator

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import src.auth.models  # noqa: F401 - register mappers on Base.metadata
import src.users.models  # noqa: F401 - register mappers on Base.metadata
from src.api.core.configs import settings
from src.api.core.database import Base

TEST_DB_NAME = "crew_shop_test"


def _swap_database(url: str, name: str) -> str:
    return url.rsplit("/", 1)[0] + "/" + name


async def _ensure_test_database() -> None:
    """Create the test database if it does not exist (CREATE DATABASE needs autocommit)."""
    admin_url = _swap_database(str(settings.get_database_url()), "postgres")
    engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with engine.connect() as conn:
            exists = await conn.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": TEST_DB_NAME},
            )
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    await _ensure_test_database()
    engine = create_async_engine(_swap_database(str(settings.get_database_url()), TEST_DB_NAME))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()
