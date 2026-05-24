"""Server-side verification of Apple and Google ID tokens.

This is the trusted boundary: downstream code relies on :class:`VerifiedIdentity`
rather than any client-sent claims. Verification is stateless and DB-free.
"""

import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from src.api.core.configs import settings
from src.auth.enums import Provider
from src.auth.exceptions import (
    InvalidProviderError,
    InvalidTokenError,
    ProviderVerificationFailedError,
)
from src.auth.identity import VerifiedIdentity

_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
_APPLE_ISSUER = "https://appleid.apple.com"
_APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"

# Cached across requests; PyJWKClient caches keys and refetches on a `kid` miss.
_apple_jwk_client = jwt.PyJWKClient(_APPLE_JWKS_URL)


def verify_provider(provider: str, token: str) -> VerifiedIdentity:
    """Verify an ID token for ``provider`` and return a normalized identity.

    Raises ``AUTH_INVALID_PROVIDER`` for an unknown provider, ``AUTH_INVALID_TOKEN``
    for a malformed/expired/badly-signed token, and ``AUTH_PROVIDER_VERIFICATION_FAILED``
    when the token is well-formed but a claim (aud/iss/sub) does not check out.
    """
    if provider == Provider.GOOGLE:
        return _verify_google(token)
    if provider == Provider.APPLE:
        return _verify_apple(token)
    raise InvalidProviderError(provider)


def _verify_google(token: str) -> VerifiedIdentity:
    try:
        # The library verifies the signature and expiry; audience and issuer are
        # checked below so the failure maps to the precise error code.
        claims = google_id_token.verify_oauth2_token(token, google_requests.Request())  # type: ignore[no-untyped-call]
    except ValueError as exc:
        raise InvalidTokenError() from exc

    if claims.get("iss") not in _GOOGLE_ISSUERS:
        raise ProviderVerificationFailedError("Unexpected Google token issuer")
    if claims.get("aud") != settings.google_client_id:
        raise ProviderVerificationFailedError("Unexpected Google token audience")
    subject = claims.get("sub")
    if not subject:
        raise ProviderVerificationFailedError("Google token missing subject")

    return VerifiedIdentity(
        provider=Provider.GOOGLE.value,
        provider_id=str(subject),
        email=claims.get("email"),
        name=claims.get("name"),
    )


def _verify_apple(token: str) -> VerifiedIdentity:
    try:
        signing_key = _apple_jwk_client.get_signing_key_from_jwt(token)
    except jwt.PyJWKClientError as exc:
        raise ProviderVerificationFailedError("Could not resolve Apple signing key") from exc
    except jwt.DecodeError as exc:
        raise InvalidTokenError() from exc

    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.apple_client_id,
            issuer=_APPLE_ISSUER,
        )
    except (jwt.InvalidAudienceError, jwt.InvalidIssuerError) as exc:
        raise ProviderVerificationFailedError("Unexpected Apple token claims") from exc
    except jwt.InvalidTokenError as exc:  # expired, bad signature, malformed, ...
        raise InvalidTokenError() from exc

    subject = claims.get("sub")
    if not subject:
        raise ProviderVerificationFailedError("Apple token missing subject")

    return VerifiedIdentity(
        provider=Provider.APPLE.value,
        provider_id=str(subject),
        email=claims.get("email"),
        name=claims.get("name"),
    )
