"""In-process stand-in for crew_auth.

Serves a JWKS backed by a test RSA key, and implements ``/oauth/exchange`` and
``/refresh-token`` with the behaviour the real service is documented to have: codes
live once, refresh tokens rotate and the presented one is revoked. Tests mint access
tokens with :func:`mint_access_token` and assert against a genuine RS256 verification
path — the crypto is real, only the network is not.
"""

import json
import time
import uuid
from dataclasses import dataclass, field

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from src.auth import crew_auth, jwks

KID = "test-key-1"
BASE_URL = "https://auth.test"
ACCESS_TTL = 900

# One keypair per test session: RSA generation is slow enough to matter across ~200 tests.
_signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_foreign_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk(private_key: rsa.RSAPrivateKey, kid: str) -> dict[str, str]:
    jwk: dict[str, str] = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
    return jwk


def jwks_document(kid: str = KID) -> dict[str, list[dict[str, str]]]:
    """The key set crew_auth would publish."""
    return {"keys": [_jwk(_signing_key, kid)]}


def mint_access_token(
    auth_user_id: uuid.UUID,
    *,
    expires_in: int = ACCESS_TTL,
    kid: str | None = KID,
    foreign_key: bool = False,
) -> str:
    """Mint an access token shaped exactly like crew_auth's: sub, iat, exp and nothing else."""
    now = int(time.time())
    claims = {"sub": str(auth_user_id), "iat": now, "exp": now + expires_in}
    headers = {"kid": kid} if kid is not None else {}
    key = _foreign_key if foreign_key else _signing_key
    return jwt.encode(claims, key, algorithm="RS256", headers=headers)


def mint_hs256_token(auth_user_id: uuid.UUID, secret: str = "public-key-substitute") -> str:
    """A symmetric token carrying a valid ``kid`` — the classic forgery against a JWKS."""
    now = int(time.time())
    claims = {"sub": str(auth_user_id), "iat": now, "exp": now + ACCESS_TTL}
    return jwt.encode(claims, secret, algorithm="HS256", headers={"kid": KID})


def auth_headers(auth_user_id: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {mint_access_token(auth_user_id)}"}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _error(code: str, message: str) -> httpx.Response:
    """crew_auth answers every failure with 400 and this body shape."""
    return httpx.Response(400, json={"error": code, "message": message})


@dataclass
class CrewAuthStub:
    """A configurable fake crew_auth. Mutate the attributes to drive failure cases."""

    codes: dict[str, uuid.UUID] = field(default_factory=dict)
    refresh_tokens: dict[str, uuid.UUID] = field(default_factory=dict)
    jwks_fetches: int = 0
    jwks_status: int = 200
    jwks_kid: str = KID
    exchange_status: int | None = None  # force a status instead of the normal flow
    refresh_status: int | None = None
    unreachable: bool = False

    def issue_code(self, auth_user_id: uuid.UUID) -> str:
        """Register a one-time login code for an identity and return it."""
        code = f"code-{uuid.uuid4().hex}"
        self.codes[code] = auth_user_id
        return code

    def issue_refresh_token(self, auth_user_id: uuid.UUID) -> str:
        token = f"refresh-{uuid.uuid4().hex}"
        self.refresh_tokens[token] = auth_user_id
        return token

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.unreachable:
            raise httpx.ConnectError("crew_auth is unreachable", request=request)

        path = request.url.path
        if path == crew_auth.JWKS_PATH:
            return self._handle_jwks()
        if path == crew_auth.EXCHANGE_PATH:
            return self._handle_exchange(json.loads(request.content))
        if path == crew_auth.REFRESH_PATH:
            return self._handle_refresh(json.loads(request.content))
        return httpx.Response(404, json={"error": "not_found", "message": path})

    def _handle_jwks(self) -> httpx.Response:
        self.jwks_fetches += 1
        if self.jwks_status != 200:
            return httpx.Response(self.jwks_status, json={"error": "internal_error"})
        return httpx.Response(
            200,
            json=jwks_document(self.jwks_kid),
            headers={"Cache-Control": "public, max-age=300"},
        )

    def _handle_exchange(self, body: dict[str, str]) -> httpx.Response:
        if self.exchange_status is not None:
            return httpx.Response(self.exchange_status, json={"error": "internal_error"})
        # The code is bound to the service that started the login, so a mismatch is
        # indistinguishable from an unknown code — exactly as crew_auth reports it.
        if body.get("service_name") != "crew_shop":
            return _error("invalid_code", "Code is invalid, expired, or already used")
        auth_user_id = self.codes.pop(body.get("code", ""), None)  # single use
        if auth_user_id is None:
            return _error("invalid_code", "Code is invalid, expired, or already used")
        return httpx.Response(
            200,
            json={
                "access_token": mint_access_token(auth_user_id),
                "refresh_token": self.issue_refresh_token(auth_user_id),
                "user_id": str(auth_user_id),
                "expires_in": ACCESS_TTL,
            },
        )

    def _handle_refresh(self, body: dict[str, str]) -> httpx.Response:
        if self.refresh_status is not None:
            return httpx.Response(self.refresh_status, json={"error": "internal_error"})
        auth_user_id = self.refresh_tokens.pop(body.get("refresh_token", ""), None)  # rotates
        if auth_user_id is None:
            return _error("invalid_refresh_token", "Refresh token is invalid or expired")
        return httpx.Response(
            200,
            json={
                "access_token": mint_access_token(auth_user_id),
                "refresh_token": self.issue_refresh_token(auth_user_id),
                "expires_in": ACCESS_TTL,
            },
        )


def install(stub: CrewAuthStub) -> None:
    """Point the crew_auth client at the stub and clear the cached key set."""
    crew_auth.set_client(
        httpx.AsyncClient(transport=httpx.MockTransport(stub.handle), base_url=BASE_URL)
    )
    jwks.reset_cache()


def uninstall() -> None:
    crew_auth.set_client(None)
    jwks.reset_cache()
