"""Integration tests for /v1/auth against an in-process crew_auth.

The stub speaks crew_auth's real wire contract (single-use codes, rotating refresh
tokens, RS256 tokens under a published JWKS), so these exercise the genuine
verification path — only the network hop is faked.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.users.models import User
from tests.integration.crew_auth_stub import (
    CrewAuthStub,
    bearer,
    mint_access_token,
    mint_hs256_token,
)

Maker = async_sessionmaker[AsyncSession]

SESSION = "/v1/auth/session"
REFRESH = "/v1/auth/refresh"
LOGOUT = "/v1/auth/logout"
ME = "/v1/users/me"


async def _user_count(maker: Maker, auth_user_id: uuid.UUID) -> int:
    async with maker() as s:
        count = await s.scalar(
            select(func.count()).select_from(User).where(User.auth_user_id == auth_user_id)
        )
        return count or 0


# ------------------------------------------------------------------ sign-in


async def test_first_sign_in_creates_the_account(
    client_db: tuple[AsyncClient, Maker], crew_auth: CrewAuthStub
) -> None:
    client, maker = client_db
    auth_user_id = uuid.uuid4()

    resp = await client.post(SESSION, json={"code": crew_auth.issue_code(auth_user_id)})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_new_user"] is True
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    # crew_auth holds no name, so a fresh account starts on a generated placeholder.
    assert body["user"]["display_name"].startswith("User-")
    assert body["user"]["email"] is None
    assert body["user"]["preferences"] == {"language": "en", "timezone": "UTC"}
    assert await _user_count(maker, auth_user_id) == 1


async def test_second_sign_in_reuses_the_account(
    client_db: tuple[AsyncClient, Maker], crew_auth: CrewAuthStub
) -> None:
    client, maker = client_db
    auth_user_id = uuid.uuid4()

    first = await client.post(SESSION, json={"code": crew_auth.issue_code(auth_user_id)})
    second = await client.post(SESSION, json={"code": crew_auth.issue_code(auth_user_id)})

    assert first.json()["is_new_user"] is True
    assert second.json()["is_new_user"] is False
    assert second.json()["user"]["id"] == first.json()["user"]["id"]
    assert await _user_count(maker, auth_user_id) == 1


async def test_replayed_code_is_rejected_cleanly(
    client: AsyncClient, crew_auth: CrewAuthStub
) -> None:
    code = crew_auth.issue_code(uuid.uuid4())
    assert (await client.post(SESSION, json={"code": code})).status_code == 200

    replay = await client.post(SESSION, json={"code": code})
    assert replay.status_code == 400
    assert replay.json()["error"]["error_code"] == "AUTH_INVALID_CODE"


async def test_unknown_code_is_rejected(client: AsyncClient) -> None:
    resp = await client.post(SESSION, json={"code": "never-issued"})
    assert resp.status_code == 400
    assert resp.json()["error"]["error_code"] == "AUTH_INVALID_CODE"


async def test_empty_code_is_a_validation_error(client: AsyncClient) -> None:
    assert (await client.post(SESSION, json={"code": ""})).status_code == 422


async def test_crew_auth_unreachable_yields_503(
    client: AsyncClient, crew_auth: CrewAuthStub
) -> None:
    crew_auth.unreachable = True
    resp = await client.post(SESSION, json={"code": "anything"})
    assert resp.status_code == 503
    assert resp.json()["error"]["error_code"] == "AUTH_UNAVAILABLE"


async def test_crew_auth_server_error_yields_503(
    client: AsyncClient, crew_auth: CrewAuthStub
) -> None:
    crew_auth.exchange_status = 500
    resp = await client.post(SESSION, json={"code": "anything"})
    assert resp.status_code == 503
    assert resp.json()["error"]["error_code"] == "AUTH_UNAVAILABLE"


# ------------------------------------------------------------------ refresh


async def test_refresh_returns_a_rotated_pair(client: AsyncClient, crew_auth: CrewAuthStub) -> None:
    session = await client.post(SESSION, json={"code": crew_auth.issue_code(uuid.uuid4())})
    original = session.json()["refresh_token"]

    resp = await client.post(REFRESH, json={"refresh_token": original})

    assert resp.status_code == 200
    assert resp.json()["refresh_token"] != original
    assert resp.json()["access_token"]


async def test_replayed_refresh_token_is_rejected(
    client: AsyncClient, crew_auth: CrewAuthStub
) -> None:
    session = await client.post(SESSION, json={"code": crew_auth.issue_code(uuid.uuid4())})
    original = session.json()["refresh_token"]
    assert (await client.post(REFRESH, json={"refresh_token": original})).status_code == 200

    replay = await client.post(REFRESH, json={"refresh_token": original})
    assert replay.status_code == 401
    assert replay.json()["error"]["error_code"] == "AUTH_INVALID_REFRESH_TOKEN"


# ------------------------------------------------------- token verification


async def test_valid_token_reaches_a_protected_endpoint(
    client_db: tuple[AsyncClient, Maker], crew_auth: CrewAuthStub
) -> None:
    client, _ = client_db
    auth_user_id = uuid.uuid4()
    session = await client.post(SESSION, json={"code": crew_auth.issue_code(auth_user_id)})

    resp = await client.get(ME, headers=bearer(session.json()["access_token"]))

    assert resp.status_code == 200
    assert resp.json()["id"] == session.json()["user"]["id"]


async def test_token_signed_by_another_key_is_rejected(client: AsyncClient) -> None:
    token = mint_access_token(uuid.uuid4(), foreign_key=True)
    resp = await client.get(ME, headers=bearer(token))
    assert resp.status_code == 401
    assert resp.json()["error"]["error_code"] == "AUTH_INVALID_TOKEN"


async def test_hs256_token_under_a_valid_kid_is_rejected(client: AsyncClient) -> None:
    """The standard forgery against published keys: sign symmetrically, claim RS256's kid."""
    resp = await client.get(ME, headers=bearer(mint_hs256_token(uuid.uuid4())))
    assert resp.status_code == 401
    assert resp.json()["error"]["error_code"] == "AUTH_INVALID_TOKEN"


async def test_token_without_kid_is_rejected(client: AsyncClient) -> None:
    resp = await client.get(ME, headers=bearer(mint_access_token(uuid.uuid4(), kid=None)))
    assert resp.status_code == 401
    assert resp.json()["error"]["error_code"] == "AUTH_INVALID_TOKEN"


async def test_token_with_unknown_kid_is_rejected(client: AsyncClient) -> None:
    resp = await client.get(ME, headers=bearer(mint_access_token(uuid.uuid4(), kid="rotated-out")))
    assert resp.status_code == 401
    assert resp.json()["error"]["error_code"] == "AUTH_INVALID_TOKEN"


async def test_expired_token_is_reported_distinctly(
    client: AsyncClient, crew_auth: CrewAuthStub
) -> None:
    """A distinct code so the client refreshes instead of dropping the user to login."""
    auth_user_id = uuid.uuid4()
    await client.post(SESSION, json={"code": crew_auth.issue_code(auth_user_id)})

    expired = mint_access_token(auth_user_id, expires_in=-60)
    resp = await client.get(ME, headers=bearer(expired))

    assert resp.status_code == 401
    assert resp.json()["error"]["error_code"] == "AUTH_TOKEN_EXPIRED"


async def test_malformed_token_is_rejected(client: AsyncClient) -> None:
    resp = await client.get(ME, headers=bearer("not-a-jwt"))
    assert resp.status_code == 401
    assert resp.json()["error"]["error_code"] == "AUTH_INVALID_TOKEN"


async def test_missing_token_is_rejected(client: AsyncClient) -> None:
    resp = await client.get(ME)
    assert resp.status_code == 401
    assert resp.json()["error"]["error_code"] == "AUTH_INVALID_TOKEN"


async def test_valid_token_without_a_shop_account_is_rejected(client: AsyncClient) -> None:
    """A genuine platform user who never completed POST /v1/auth/session."""
    resp = await client.get(ME, headers=bearer(mint_access_token(uuid.uuid4())))
    assert resp.status_code == 401
    assert resp.json()["error"]["error_code"] == "AUTH_ACCOUNT_NOT_FOUND"


async def test_deactivated_account_is_rejected(
    client_db: tuple[AsyncClient, Maker], crew_auth: CrewAuthStub
) -> None:
    client, maker = client_db
    auth_user_id = uuid.uuid4()
    session = await client.post(SESSION, json={"code": crew_auth.issue_code(auth_user_id)})

    async with maker() as s:
        user = await s.scalar(select(User).where(User.auth_user_id == auth_user_id))
        assert user is not None
        user.is_active = False
        await s.commit()

    resp = await client.get(ME, headers=bearer(session.json()["access_token"]))
    assert resp.status_code == 401
    assert resp.json()["error"]["error_code"] == "AUTH_ACCOUNT_INACTIVE"


async def test_jwks_is_fetched_once_across_many_requests(
    client: AsyncClient, crew_auth: CrewAuthStub
) -> None:
    """Verification is local: the key set is cached, never refetched per request."""
    auth_user_id = uuid.uuid4()
    await client.post(SESSION, json={"code": crew_auth.issue_code(auth_user_id)})
    crew_auth.jwks_fetches = 0

    for _ in range(3):
        assert (await client.get(ME, headers=bearer(mint_access_token(auth_user_id)))).status_code

    assert crew_auth.jwks_fetches == 1


async def test_rotated_key_is_picked_up_without_waiting_for_expiry(
    client: AsyncClient, crew_auth: CrewAuthStub
) -> None:
    """A cache populated before a rotation must not reject valid tokens until it expires."""
    auth_user_id = uuid.uuid4()
    session = await client.post(SESSION, json={"code": crew_auth.issue_code(auth_user_id)})
    assert (await client.get(ME, headers=bearer(session.json()["access_token"]))).status_code == 200

    crew_auth.jwks_kid = "rotated-key"
    resp = await client.get(ME, headers=bearer(mint_access_token(auth_user_id, kid="rotated-key")))

    assert resp.status_code == 200


async def test_unknown_kid_refetches_at_most_once(
    client: AsyncClient, crew_auth: CrewAuthStub
) -> None:
    """A forged kid must not become a way to hammer crew_auth."""
    await client.get(ME, headers=bearer(mint_access_token(uuid.uuid4())))  # warms the cache
    crew_auth.jwks_fetches = 0

    for _ in range(4):
        resp = await client.get(ME, headers=bearer(mint_access_token(uuid.uuid4(), kid="forged")))
        assert resp.status_code == 401

    assert crew_auth.jwks_fetches == 1


# ------------------------------------------------------------------- logout


async def test_logout_requires_authentication(client: AsyncClient) -> None:
    assert (await client.post(LOGOUT)).status_code == 401


async def test_logout_succeeds_without_revoking_anything(
    client: AsyncClient, crew_auth: CrewAuthStub
) -> None:
    """crew_auth exposes no revoke endpoint; the token stays valid by design, not oversight."""
    session = await client.post(SESSION, json={"code": crew_auth.issue_code(uuid.uuid4())})
    headers = bearer(session.json()["access_token"])

    assert (await client.post(LOGOUT, headers=headers)).status_code == 204
    assert (await client.get(ME, headers=headers)).status_code == 200


# -------------------------------------------------------------- old surface


async def test_retired_endpoints_are_gone(client: AsyncClient) -> None:
    for path in ("/v1/auth/login", "/v1/auth/register", "/v1/auth/token/refresh"):
        assert (await client.post(path, json={})).status_code == 404, path
