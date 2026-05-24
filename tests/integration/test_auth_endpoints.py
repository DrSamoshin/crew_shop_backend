"""Integration tests for the /v1/auth endpoints (provider verification mocked)."""

import pytest
from httpx import AsyncClient

from src.auth import providers
from src.auth.cookies import CSRF_COOKIE, CSRF_HEADER, REFRESH_COOKIE
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


async def _register(client: AsyncClient) -> None:
    resp = await client.post("/v1/auth/register", json=BODY)
    assert resp.status_code == 201


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
    assert body["expires_in"] > 0
    assert resp.cookies.get(REFRESH_COOKIE)
    assert resp.cookies.get(CSRF_COOKIE)


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
    assert resp.json()["is_new_user"] is False


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


async def test_refresh_with_cookie_rotates(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_identity(monkeypatch)
    reg = await client.post("/v1/auth/register", json=BODY)
    csrf = reg.cookies.get(CSRF_COOKIE)
    resp = await client.post("/v1/auth/token/refresh", headers={CSRF_HEADER: csrf})
    assert resp.status_code == 200
    assert resp.json()["access_token"]
    assert resp.cookies.get(REFRESH_COOKIE)  # rotated


async def test_refresh_without_csrf_rejected(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_identity(monkeypatch)
    await client.post("/v1/auth/register", json=BODY)
    resp = await client.post("/v1/auth/token/refresh")  # no CSRF header
    assert resp.status_code == 403
    assert resp.json()["error"]["error_code"] == "AUTH_CSRF_INVALID"


async def test_logout_revokes_session(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_identity(monkeypatch)
    reg = await client.post("/v1/auth/register", json=BODY)
    access = reg.json()["access_token"]
    refresh_cookie = reg.cookies.get(REFRESH_COOKIE)
    csrf = reg.cookies.get(CSRF_COOKIE)

    resp = await client.post(
        "/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}", CSRF_HEADER: csrf},
    )
    assert resp.status_code == 204

    # The session is revoked: replaying the old refresh token fails (logout cleared the
    # jar, so supply the captured cookies explicitly for this one request).
    resp2 = await client.post(
        "/v1/auth/token/refresh",
        headers={CSRF_HEADER: csrf},
        cookies={REFRESH_COOKIE: refresh_cookie, CSRF_COOKIE: csrf},
    )
    assert resp2.status_code == 401
    assert resp2.json()["error"]["error_code"] == "AUTH_SESSION_REVOKED"
