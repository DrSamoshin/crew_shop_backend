"""Integration tests for the saved-payment-methods API (/v1/users/me/payment-methods)."""

import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.api.core.configs import settings as app_settings
from src.payments.models import PaymentMethod
from src.users.models import User
from tests.integration.crew_auth_stub import mint_access_token

Maker = async_sessionmaker[AsyncSession]


@dataclass(frozen=True, slots=True)
class Env:
    user_id: uuid.UUID
    token: str


async def _authed_user(maker: Maker) -> Env:
    async with maker() as s:
        user = User(display_name="User", auth_user_id=uuid.uuid4())
        s.add(user)
        await s.flush()
        access = mint_access_token(user.auth_user_id)
        await s.commit()
        return Env(user.id, access)


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _provider_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_settings, "payment_provider_secret", "test")


async def test_save_method_first_becomes_default(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    env = await _authed_user(maker)

    resp = await client.post(
        "/v1/users/me/payment-methods",
        json={"intent_token": "tok-fake-1"},
        headers=_auth(env.token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["provider"] == "fake"
    assert body["brand"] == "visa"
    assert body["last4"] == "4242"
    assert body["is_default"] is True


async def test_save_method_second_with_is_default_replaces(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    env = await _authed_user(maker)
    first = await client.post(
        "/v1/users/me/payment-methods",
        json={"intent_token": "tok-1"},
        headers=_auth(env.token),
    )
    second = await client.post(
        "/v1/users/me/payment-methods",
        json={"intent_token": "tok-2", "is_default": True},
        headers=_auth(env.token),
    )
    assert second.status_code == 201
    assert second.json()["is_default"] is True

    listed = await client.get("/v1/users/me/payment-methods", headers=_auth(env.token))
    items = {m["id"]: m for m in listed.json()["items"]}
    assert items[first.json()["id"]]["is_default"] is False
    assert items[second.json()["id"]]["is_default"] is True


async def test_list_returns_caller_methods_only(
    client_db: tuple[AsyncClient, Maker],
) -> None:
    client, maker = client_db
    env = await _authed_user(maker)
    other = await _authed_user(maker)
    await client.post(
        "/v1/users/me/payment-methods",
        json={"intent_token": "tok-mine"},
        headers=_auth(env.token),
    )
    await client.post(
        "/v1/users/me/payment-methods",
        json={"intent_token": "tok-other"},
        headers=_auth(other.token),
    )

    mine = await client.get("/v1/users/me/payment-methods", headers=_auth(env.token))
    assert mine.json()["total"] == 1


async def test_set_default_switches(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _authed_user(maker)
    first = await client.post(
        "/v1/users/me/payment-methods",
        json={"intent_token": "tok-1"},
        headers=_auth(env.token),
    )
    second = await client.post(
        "/v1/users/me/payment-methods",
        json={"intent_token": "tok-2"},
        headers=_auth(env.token),
    )
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    resp = await client.post(
        f"/v1/users/me/payment-methods/{second_id}/default", headers=_auth(env.token)
    )
    assert resp.status_code == 200
    assert resp.json()["is_default"] is True

    listed = await client.get("/v1/users/me/payment-methods", headers=_auth(env.token))
    items = {m["id"]: m for m in listed.json()["items"]}
    assert items[first_id]["is_default"] is False
    assert items[second_id]["is_default"] is True


async def test_delete_method_promotes_next(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _authed_user(maker)
    first = await client.post(
        "/v1/users/me/payment-methods",
        json={"intent_token": "tok-1"},
        headers=_auth(env.token),
    )
    await client.post(
        "/v1/users/me/payment-methods",
        json={"intent_token": "tok-2"},
        headers=_auth(env.token),
    )

    resp = await client.delete(
        f"/v1/users/me/payment-methods/{first.json()['id']}", headers=_auth(env.token)
    )
    assert resp.status_code == 204

    listed = await client.get("/v1/users/me/payment-methods", headers=_auth(env.token))
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["is_default"] is True


async def test_delete_others_method_404(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _authed_user(maker)
    other = await _authed_user(maker)
    saved = await client.post(
        "/v1/users/me/payment-methods",
        json={"intent_token": "tok-other"},
        headers=_auth(other.token),
    )

    resp = await client.delete(
        f"/v1/users/me/payment-methods/{saved.json()['id']}", headers=_auth(env.token)
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["error_code"] == "PAYMENT_METHOD_NOT_FOUND"


async def test_requires_auth(client_db: tuple[AsyncClient, Maker]) -> None:
    client, _ = client_db
    resp = await client.get("/v1/users/me/payment-methods")
    assert resp.status_code == 401


async def test_cascade_on_user_delete(client_db: tuple[AsyncClient, Maker]) -> None:
    client, maker = client_db
    env = await _authed_user(maker)
    await client.post(
        "/v1/users/me/payment-methods",
        json={"intent_token": "tok"},
        headers=_auth(env.token),
    )
    async with maker() as s:
        user = await s.get(User, env.user_id)
        assert user is not None
        await s.delete(user)
        await s.commit()
    async with maker() as s:
        rows = (
            (await s.execute(select(PaymentMethod).where(PaymentMethod.user_id == env.user_id)))
            .scalars()
            .all()
        )
        assert rows == []
