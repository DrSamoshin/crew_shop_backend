from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict

import src.bootstrap  # noqa: F401 - load .env before Settings is instantiated

_ASYNC_SCHEME = "postgresql+asyncpg"
# libpq spells the SSL mode `sslmode`; asyncpg's connect() only knows `ssl` and has no
# **kwargs, so an untranslated `sslmode` is a TypeError on the first connection.
_SSL_MODE_TO_ASYNCPG = {
    "disable": "disable",
    "allow": "prefer",
    "prefer": "prefer",
    "require": "require",
    "verify-ca": "verify-ca",
    "verify-full": "verify-full",
}


def normalize_database_url(url: str) -> str:
    """Adapt a stock libpq DSN to the async driver this service uses.

    Managed providers hand out `postgresql://…?sslmode=require` — DigitalOcean's Terraform
    output included. SQLAlchemy would resolve that to psycopg2 and fail on import, so the
    scheme is pinned to asyncpg and the SSL parameter translated. A DSN that already names
    a driver is left alone: an explicit choice beats a guess.
    """
    parsed = urlparse(url)
    if parsed.scheme != "postgresql":
        return url

    query = parse_qsl(parsed.query, keep_blank_values=True)
    translated = [
        ("ssl", _SSL_MODE_TO_ASYNCPG.get(value, value)) if key == "sslmode" else (key, value)
        for key, value in query
    ]
    return urlunparse(parsed._replace(scheme=_ASYNC_SCHEME, query=urlencode(translated)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # Application
    app_title: str = "crew_shop_backend"
    app_version: str = "0.1.0"
    app_host: str = "0.0.0.0"
    app_port: int = 8080

    # Environment
    env: Literal["dev", "stage", "prod"] = "dev"
    log_level: str = "INFO"
    cors_origins: str = ""
    workers: int = 4

    # crew_auth (platform identity provider). The service exchanges one-time codes here
    # and verifies its RS256 access tokens locally against the published JWKS.
    crew_auth_url: str = "https://auth.crewservices.org"
    # Must match the RETURN_URIS_<SERVICE> key registered with crew_auth.
    crew_auth_service_name: str = "crew_shop"
    crew_auth_timeout: float = 5.0  # seconds, per server-to-server call

    # Admin S2S (crew_admin → admin API). Per-environment shared service token; unset
    # disables the admin API entirely (every request is rejected).
    admin_service_token: str | None = None

    # Payment provider callback secret. The FakeProvider verifies webhook signatures with this
    # value; a real provider plugs its own scheme in. Unset → callbacks are rejected.
    payment_provider_secret: str | None = None

    # Database. One complete DSN in every environment: locally from .env.dev, in the
    # cluster from the crew-shop-db Secret. The old stage/prod path assembled a Cloud SQL
    # Unix-socket URL from four parts; managed PostgreSQL is reached over plain TCP.
    database_url: str | None = None

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def get_database_url(self) -> str:
        """Return the configured DSN, or fail loudly rather than booting unconfigured."""
        if not self.database_url:
            raise ValueError(f"DATABASE_URL is required (env={self.env})")
        return normalize_database_url(self.database_url)

    def get_database_url_masked(self) -> str:
        """Get the database URL with the password masked, for logging."""
        if not self.database_url:
            return "not configured"
        parsed = urlparse(self.database_url)
        if parsed.password and parsed.hostname:
            netloc = f"{parsed.username}:***@{parsed.hostname}"
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            return urlunparse(parsed._replace(netloc=netloc))
        return self.database_url


settings = Settings()
