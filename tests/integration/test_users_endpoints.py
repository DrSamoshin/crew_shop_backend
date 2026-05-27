"""Integration tests for the user account API (/v1/users/me)."""

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.auth import sessions
from src.auth.models import OAuthAccount
from src.users.models import User, UserPreferences

Maker = async_sessionmaker[AsyncSession]


async def _authed_user(
    maker: Maker, *, display_name: str = "Anna", email: str | None = "anna@example.com"
) -> tuple[uuid.UUID, str]:
    async with maker() as s:
        user = User(display_name=display_name, email=email)
        s.add(user)
        await s.flush()
        s.add(OAuthAccount(user_id=user.id, provider="google", provider_id=f"g-{uuid.uuid4()}"))
        s.add(UserPreferences(user_id=user.id))  # defaults: en / UTC
        access, _ = await sessions.create_session(s, user.id)
        await s.commit()
        return user.id, access


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_get_me(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    _, token = await _authed_user(maker)

    resp = await client.get("/v1/users/me", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Anna"
    assert data["email"] == "anna@example.com"
    assert data["is_active"] is True
    assert data["preferences"] == {"language": "en", "timezone": "UTC"}


async def test_get_me_requires_auth(client_db: tuple[AsyncClient, Maker]) -> None:
    client, _ = client_db
    resp = await client.get("/v1/users/me")
    assert resp.status_code == 401


async def test_update_profile(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    _, token = await _authed_user(maker)

    resp = await client.put(
        "/v1/users/me",
        json={"display_name": "Anna K.", "email": "anna.k@example.com"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["display_name"] == "Anna K."
    assert data["email"] == "anna.k@example.com"


async def test_update_profile_can_clear_email(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    _, token = await _authed_user(maker)

    resp = await client.put("/v1/users/me", json={"email": None}, headers=_auth(token))
    assert resp.status_code == 200
    assert resp.json()["email"] is None


async def test_update_profile_empty_display_name_400(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    _, token = await _authed_user(maker)

    resp = await client.put("/v1/users/me", json={"display_name": "  "}, headers=_auth(token))
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "USER_INVALID_DISPLAY_NAME"


async def test_update_profile_invalid_email_400(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    _, token = await _authed_user(maker)

    resp = await client.put("/v1/users/me", json={"email": "not-an-email"}, headers=_auth(token))
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "USER_INVALID_EMAIL"


async def test_update_preferences(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    _, token = await _authed_user(maker)

    resp = await client.put(
        "/v1/users/me/preferences",
        json={"language": "uk", "timezone": "Europe/Kyiv"},
        headers=_auth(token),
    )
    assert resp.status_code == 200
    assert resp.json() == {"language": "uk", "timezone": "Europe/Kyiv"}


async def test_update_preferences_invalid_language_400(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    _, token = await _authed_user(maker)

    resp = await client.put(
        "/v1/users/me/preferences", json={"language": "fr"}, headers=_auth(token)
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "USER_INVALID_PREFERENCE"


async def test_update_preferences_invalid_timezone_400(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    _, token = await _authed_user(maker)

    resp = await client.put(
        "/v1/users/me/preferences", json={"timezone": "Mars/Olympus"}, headers=_auth(token)
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "USER_INVALID_PREFERENCE"


async def test_delete_account_hard_anonymizes(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    user_id, token = await _authed_user(maker)

    resp = await client.delete("/v1/users/me", headers=_auth(token))
    assert resp.status_code == 204

    async with maker() as s:
        user = await s.get(User, user_id)
        assert user is not None
        assert user.email is None
        assert user.display_name.startswith("User-")
        assert user.is_active is False
        oauth = await s.scalar(
            select(func.count()).select_from(OAuthAccount).where(OAuthAccount.user_id == user_id)
        )
        prefs = await s.scalar(
            select(func.count())
            .select_from(UserPreferences)
            .where(UserPreferences.user_id == user_id)
        )
        assert oauth == 0
        assert prefs == 0

    # Sessions revoked -> the access token no longer authenticates.
    after = await client.get("/v1/users/me", headers=_auth(token))
    assert after.status_code == 401


async def test_delete_account_soft_deactivates(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    user_id, token = await _authed_user(maker)

    resp = await client.delete("/v1/users/me?mode=soft", headers=_auth(token))
    assert resp.status_code == 204

    async with maker() as s:
        user = await s.get(User, user_id)
        assert user is not None
        assert user.is_active is False
        assert user.email == "anna@example.com"  # preserved
        oauth = await s.scalar(
            select(func.count()).select_from(OAuthAccount).where(OAuthAccount.user_id == user_id)
        )
        prefs = await s.scalar(
            select(func.count())
            .select_from(UserPreferences)
            .where(UserPreferences.user_id == user_id)
        )
        assert oauth == 1  # preserved for recovery
        assert prefs == 1
