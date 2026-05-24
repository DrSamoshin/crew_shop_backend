"""Unit tests for the app JWT service (encode/decode, no DB)."""

import uuid

import pytest

from src.auth import tokens
from src.auth.exceptions import InvalidTokenError


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    token = tokens.encode_access(user_id, session_id)
    claims = tokens.decode(token, expected_type=tokens.TOKEN_TYPE_ACCESS)
    assert claims["sub"] == str(user_id)
    assert claims["session_id"] == str(session_id)
    assert claims["type"] == tokens.TOKEN_TYPE_ACCESS
    assert "jti" in claims


def test_refresh_token_roundtrip() -> None:
    session_id = uuid.uuid4()
    refresh_jti = uuid.uuid4()
    token = tokens.encode_refresh(session_id, refresh_jti)
    claims = tokens.decode(token, expected_type=tokens.TOKEN_TYPE_REFRESH)
    assert claims["session_id"] == str(session_id)
    assert claims["refresh_jti"] == str(refresh_jti)


def test_expired_access_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tokens.settings, "access_token_ttl", -10)
    token = tokens.encode_access(uuid.uuid4(), uuid.uuid4())
    with pytest.raises(InvalidTokenError):
        tokens.decode(token, expected_type=tokens.TOKEN_TYPE_ACCESS)


def test_tampered_token_rejected() -> None:
    token = tokens.encode_access(uuid.uuid4(), uuid.uuid4())
    header, payload, signature = token.split(".")
    # Flip the first signature char (all 6 bits significant) so the bytes change.
    tampered_sig = ("A" if signature[0] != "A" else "B") + signature[1:]
    tampered = f"{header}.{payload}.{tampered_sig}"
    with pytest.raises(InvalidTokenError):
        tokens.decode(tampered, expected_type=tokens.TOKEN_TYPE_ACCESS)


def test_wrong_token_type_rejected() -> None:
    token = tokens.encode_access(uuid.uuid4(), uuid.uuid4())
    with pytest.raises(InvalidTokenError):
        tokens.decode(token, expected_type=tokens.TOKEN_TYPE_REFRESH)


def test_wrong_secret_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    token = tokens.encode_access(uuid.uuid4(), uuid.uuid4())
    monkeypatch.setattr(tokens.settings, "secret_key", "another-insecure-secret-key-32-bytes-min")
    with pytest.raises(InvalidTokenError):
        tokens.decode(token, expected_type=tokens.TOKEN_TYPE_ACCESS)
