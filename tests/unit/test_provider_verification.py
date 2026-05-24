"""Unit tests for OAuth provider verification (network mocked, no real calls)."""

from types import SimpleNamespace
from typing import Any

import jwt
import pytest

from src.auth import providers
from src.auth.exceptions import (
    InvalidProviderError,
    InvalidTokenError,
    ProviderVerificationFailedError,
)

GOOGLE_CID = "google-client-id.apps.googleusercontent.com"
APPLE_CID = "com.crewshop.app"


@pytest.fixture(autouse=True)
def _client_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(providers.settings, "google_client_id", GOOGLE_CID)
    monkeypatch.setattr(providers.settings, "apple_client_id", APPLE_CID)


def _patch_google(monkeypatch: pytest.MonkeyPatch, result: Any) -> None:
    def fake(token: str, request: object) -> dict[str, Any]:
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(providers.google_id_token, "verify_oauth2_token", fake)


def _patch_apple(
    monkeypatch: pytest.MonkeyPatch,
    *,
    decode: Any,
    signing_key: Any = None,
) -> None:
    key = signing_key if signing_key is not None else SimpleNamespace(key="fake-key")

    def fake_get_key(token: str) -> object:
        if isinstance(key, Exception):
            raise key
        return key

    def fake_decode(token: str, key: object, **kwargs: Any) -> dict[str, Any]:
        if isinstance(decode, Exception):
            raise decode
        return decode

    monkeypatch.setattr(providers._apple_jwk_client, "get_signing_key_from_jwt", fake_get_key)
    monkeypatch.setattr(providers.jwt, "decode", fake_decode)


# --- Google ---------------------------------------------------------------


def test_google_valid_token_returns_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_google(
        monkeypatch,
        {
            "iss": "https://accounts.google.com",
            "aud": GOOGLE_CID,
            "sub": "google-sub-123",
            "email": "alice@example.com",
            "name": "Alice",
        },
    )
    identity = providers.verify_provider("google", "tok")
    assert identity.provider == "google"
    assert identity.provider_id == "google-sub-123"
    assert identity.email == "alice@example.com"
    assert identity.name == "Alice"


def test_google_bad_signature_raises_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_google(monkeypatch, ValueError("Invalid token signature"))
    with pytest.raises(InvalidTokenError):
        providers.verify_provider("google", "tok")


def test_google_wrong_audience_raises_verification_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_google(
        monkeypatch,
        {"iss": "https://accounts.google.com", "aud": "someone-else", "sub": "x"},
    )
    with pytest.raises(ProviderVerificationFailedError):
        providers.verify_provider("google", "tok")


def test_google_wrong_issuer_raises_verification_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_google(monkeypatch, {"iss": "https://evil.example.com", "aud": GOOGLE_CID, "sub": "x"})
    with pytest.raises(ProviderVerificationFailedError):
        providers.verify_provider("google", "tok")


# --- Apple ----------------------------------------------------------------


def test_apple_valid_token_returns_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_apple(
        monkeypatch,
        decode={"sub": "apple-sub-456", "email": "bob@example.com", "name": "Bob"},
    )
    identity = providers.verify_provider("apple", "tok")
    assert identity.provider == "apple"
    assert identity.provider_id == "apple-sub-456"
    assert identity.email == "bob@example.com"
    assert identity.name == "Bob"


def test_apple_hidden_email_and_name_are_none(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_apple(monkeypatch, decode={"sub": "apple-sub-456"})
    identity = providers.verify_provider("apple", "tok")
    assert identity.email is None
    assert identity.name is None


def test_apple_expired_raises_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_apple(monkeypatch, decode=jwt.ExpiredSignatureError("expired"))
    with pytest.raises(InvalidTokenError):
        providers.verify_provider("apple", "tok")


def test_apple_wrong_audience_raises_verification_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_apple(monkeypatch, decode=jwt.InvalidAudienceError("bad aud"))
    with pytest.raises(ProviderVerificationFailedError):
        providers.verify_provider("apple", "tok")


def test_apple_jwks_resolution_failure_raises_verification_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_apple(
        monkeypatch,
        decode={"sub": "unused"},
        signing_key=jwt.PyJWKClientError("no matching key"),
    )
    with pytest.raises(ProviderVerificationFailedError):
        providers.verify_provider("apple", "tok")


# --- Dispatch -------------------------------------------------------------


def test_unsupported_provider_raises_invalid_provider() -> None:
    with pytest.raises(InvalidProviderError):
        providers.verify_provider("facebook", "tok")
