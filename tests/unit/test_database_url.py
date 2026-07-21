"""The DSN handed out by managed PostgreSQL must reach the async driver intact.

DigitalOcean's Terraform output is `postgresql://…?sslmode=require`. Left alone, SQLAlchemy
resolves that to psycopg2 (ModuleNotFoundError at engine creation) and passes `sslmode`
straight to `asyncpg.connect()`, which has no such argument and no `**kwargs`.
"""

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from src.api.core.configs import normalize_database_url

DO_DSN = "postgresql://crew_shop:s3cret@private-db.internal:25060/crew_shop?sslmode=require"


def _connect_kwargs(url: str) -> dict[str, object]:
    """The keyword arguments SQLAlchemy would hand to ``asyncpg.connect()``."""
    _, kwargs = postgresql.asyncpg.dialect().create_connect_args(make_url(url))
    return dict(kwargs)


def test_managed_dsn_becomes_connectable() -> None:
    normalized = normalize_database_url(DO_DSN)

    assert normalized.startswith("postgresql+asyncpg://")
    create_async_engine(normalized)  # would raise ModuleNotFoundError on the raw DSN

    kwargs = _connect_kwargs(normalized)
    assert kwargs["ssl"] == "require"
    assert "sslmode" not in kwargs  # asyncpg.connect() would reject it
    assert kwargs["host"] == "private-db.internal"
    assert kwargs["port"] == 25060
    assert kwargs["database"] == "crew_shop"
    assert kwargs["password"] == "s3cret"


@pytest.mark.parametrize(
    ("sslmode", "expected"),
    [
        ("require", "require"),
        ("verify-full", "verify-full"),
        ("disable", "disable"),
        # asyncpg has no `allow`; `prefer` is its nearest opportunistic equivalent.
        ("allow", "prefer"),
    ],
)
def test_ssl_modes_are_translated(sslmode: str, expected: str) -> None:
    url = normalize_database_url(f"postgresql://u:p@h:5432/db?sslmode={sslmode}")
    assert _connect_kwargs(url)["ssl"] == expected


def test_explicit_driver_is_left_alone() -> None:
    """An operator who named a driver made a choice; do not second-guess it."""
    dsn = "postgresql+asyncpg://u:p@h:5432/db"
    assert normalize_database_url(dsn) == dsn


def test_local_dev_dsn_is_unchanged() -> None:
    dsn = "postgresql+asyncpg://crew_shop:crew_shop@localhost:5432/crew_shop_db"
    assert normalize_database_url(dsn) == dsn


def test_other_query_parameters_survive() -> None:
    url = normalize_database_url(
        "postgresql://u:p@h:5432/db?sslmode=require&application_name=crew_shop"
    )
    kwargs = _connect_kwargs(url)
    assert kwargs["ssl"] == "require"
    assert kwargs["application_name"] == "crew_shop"  # only sslmode is rewritten
