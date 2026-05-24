"""Integration tests for the /v1/auth endpoints (provider verification mocked)."""

from typing import Any

import pytest
from httpx import AsyncClient

from src.auth import providers
from src.auth.exceptions import InvalidTokenError
from src.auth.identity import VerifiedIdentity

DEFAULT_IDENTITY = VerifiedIdentity(
    provider="google", provider_id="google-1", email="alice@example.com", name="Alice"
)
BODY = {"provider": "google", "token": "provider-token"}


def _patch_identity(
    monkeypatch: pytest.MonkeyPatch,
    identity: VerifiedIdentity = DEFAULT_IDENTITY,
    error: Exception | None = None,
) -> None:
    def fake(provider: str, token: str) -> VerifiedIdentity:
        if error is not None:
            raise error
        return identity

    monkeypatch.setattr(providers, "verify_provider", fake)


async def _register(client: AsyncClient) -> dict[str, Any]:
    resp = await client.post("/v1/auth/register", json=BODY)
    assert resp.status_code == 201
    return resp.json()


async def test_register_creates_account(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_identity(monkeypatch)
    resp = await client.post("/v1/auth/register", json=BODY)
    assert resp.status_code == 201
    body = resp.json()
    assert body["is_new_user"] is True
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["expires_in"] > 0


async def test_register_duplicate_returns_409(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_identity(monkeypatch)
    await _register(client)
    resp = await client.post("/v1/auth/register", json=BODY)
    assert resp.status_code == 409
    assert resp.json()["error"]["error_code"] == "AUTH_OAUTH_ACCOUNT_EXISTS"


async def test_login_existing_returns_tokens(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_identity(monkeypatch)
    await _register(client)
    resp = await client.post("/v1/auth/login", json=BODY)
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_new_user"] is False
    assert body["access_token"]
    assert body["refresh_token"]


async def test_login_unknown_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_identity(monkeypatch)
    resp = await client.post("/v1/auth/login", json=BODY)
    assert resp.status_code == 404
    assert resp.json()["error"]["error_code"] == "AUTH_USER_NOT_FOUND"


async def test_unknown_provider_returns_400(client: AsyncClient) -> None:
    # Not patched: the real dispatcher rejects an unknown provider without any network call.
    resp = await client.post("/v1/auth/login", json={"provider": "facebook", "token": "x"})
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "AUTH_INVALID_PROVIDER"


async def test_invalid_provider_token_returns_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_identity(monkeypatch, error=InvalidTokenError())
    resp = await client.post("/v1/auth/login", json=BODY)
    assert resp.status_code == 401
    assert resp.json()["error"]["error_code"] == "AUTH_INVALID_TOKEN"


async def test_refresh_rotates(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_identity(monkeypatch)
    reg = await _register(client)
    old_refresh = reg["refresh_token"]
    resp = await client.post("/v1/auth/token/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["refresh_token"] != old_refresh  # rotated


async def test_refresh_reuse_revokes_session(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_identity(monkeypatch)
    reg = await _register(client)
    old_refresh = reg["refresh_token"]
    first = await client.post("/v1/auth/token/refresh", json={"refresh_token": old_refresh})
    assert first.status_code == 200
    # Replaying the now-rotated refresh token is reuse: the whole session is revoked.
    replay = await client.post("/v1/auth/token/refresh", json={"refresh_token": old_refresh})
    assert replay.status_code == 401
    assert replay.json()["error"]["error_code"] == "AUTH_SESSION_REVOKED"


async def test_logout_revokes_session(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_identity(monkeypatch)
    reg = await _register(client)
    access = reg["access_token"]
    refresh = reg["refresh_token"]

    resp = await client.post("/v1/auth/logout", headers={"Authorization": f"Bearer {access}"})
    assert resp.status_code == 204

    # The session is revoked: the refresh token no longer works.
    resp2 = await client.post("/v1/auth/token/refresh", json={"refresh_token": refresh})
    assert resp2.status_code == 401
    assert resp2.json()["error"]["error_code"] == "AUTH_SESSION_REVOKED"


async def test_logout_requires_bearer(client: AsyncClient) -> None:
    resp = await client.post("/v1/auth/logout")
    assert resp.status_code == 401
    assert resp.json()["error"]["error_code"] == "AUTH_INVALID_TOKEN"
