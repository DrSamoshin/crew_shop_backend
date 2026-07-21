from typing import Literal
from urllib.parse import urlparse, urlunparse

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

import src.bootstrap  # noqa: F401 - load .env before Settings is instantiated


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

    # Database - dev (simple URL string)
    database_url: str | None = None

    # Database - stage/prod (Cloud SQL connection parts)
    database_user: str | None = None
    database_password: str | None = None
    database_name: str | None = None
    database_host: str | None = None  # Cloud SQL socket path

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def get_database_url(self) -> str | URL:
        """Build the database URL based on the environment."""
        if self.env == "dev":
            if not self.database_url:
                raise ValueError("DATABASE_URL is required for the dev environment")
            return self.database_url

        if not all(
            [self.database_user, self.database_password, self.database_name, self.database_host]
        ):
            raise ValueError(
                "DATABASE_USER, DATABASE_PASSWORD, DATABASE_NAME, and DATABASE_HOST "
                "are required for stage/prod environments"
            )
        return URL.create(
            "postgresql+asyncpg",
            username=self.database_user,
            password=self.database_password,  # automatically URL-encoded
            database=self.database_name,
            query={"host": f"/cloudsql/{self.database_host}"},
        )

    def get_database_url_masked(self) -> str:
        """Get the database URL with the password masked, for logging."""
        if self.env == "dev":
            if not self.database_url:
                return "not configured"
            parsed = urlparse(self.database_url)
            if parsed.password and parsed.hostname:
                netloc = f"{parsed.username}:***@{parsed.hostname}"
                if parsed.port:
                    netloc = f"{netloc}:{parsed.port}"
                return urlunparse(parsed._replace(netloc=netloc))
            return self.database_url
        return (
            f"postgresql+asyncpg://{self.database_user}:***@"
            f"/cloudsql/{self.database_host}/{self.database_name}"
        )


settings = Settings()
