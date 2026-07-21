"""Integration test harness: a session bound to a real PostgreSQL test database.

Runs against the Docker Postgres (see docker-compose.yml). Uses a dedicated
`crew_shop_test` database so it never touches dev data, recreating the schema
from the models before each test for isolation.
"""

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import src.catalog.models  # noqa: F401 - register mappers on Base.metadata
import src.orders.models  # noqa: F401 - register mappers on Base.metadata
import src.payments.models  # noqa: F401 - register mappers on Base.metadata
import src.points.models  # noqa: F401 - register mappers on Base.metadata
import src.ratings.models  # noqa: F401 - register mappers on Base.metadata
import src.subscriptions.models  # noqa: F401 - register mappers on Base.metadata
import src.users.models  # noqa: F401 - register mappers on Base.metadata
from scripts import seed_dev
from src.api.app import create_app
from src.api.core.configs import settings
from src.api.core.database import Base, get_db
from tests.integration import crew_auth_stub

TEST_DB_NAME = "crew_shop_test"


@pytest_asyncio.fixture(autouse=True)
async def crew_auth() -> AsyncGenerator[crew_auth_stub.CrewAuthStub]:
    """Serve crew_auth in-process for every test, so token verification is never networked.

    Autouse because any authenticated request needs the JWKS; tests that care about the
    exchange or refresh behaviour take the stub as an argument and configure it.
    """
    stub = crew_auth_stub.CrewAuthStub()
    crew_auth_stub.install(stub)
    try:
        yield stub
    finally:
        crew_auth_stub.uninstall()


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


async def _fresh_test_engine() -> AsyncEngine:
    await _ensure_test_database()
    engine = create_async_engine(_swap_database(str(settings.get_database_url()), TEST_DB_NAME))
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    return engine


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession]:
    engine = await _fresh_test_engine()
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """An HTTP client against the app, wired to the fresh test database via get_db override."""
    engine = await _fresh_test_engine()
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http_client:
            yield http_client
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest_asyncio.fixture
async def client_db() -> AsyncGenerator[tuple[AsyncClient, async_sessionmaker[AsyncSession]]]:
    """A client plus the session maker bound to the *same* fresh test database.

    Lets a test seed/inspect rows (and mint auth tokens) directly while exercising the HTTP API.
    """
    engine = await _fresh_test_engine()
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http_client:
            yield http_client, maker
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


@pytest_asyncio.fixture
async def seeded_client() -> AsyncGenerator[AsyncClient]:
    """A client whose fresh test database is loaded with the deterministic dev seed."""
    engine = await _fresh_test_engine()
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with maker() as session:
        await seed_dev.seed_users(session)
        await seed_dev.seed_catalog(session)
        await seed_dev.seed_ratings(session)
        await session.commit()

    async def _override_get_db() -> AsyncGenerator[AsyncSession]:
        async with maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http_client:
            yield http_client
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()
