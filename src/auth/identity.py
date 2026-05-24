"""Normalized identity returned by provider verification."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VerifiedIdentity:
    """A provider identity proven by a verified ID token.

    ``email`` and ``name`` are optional: Apple's privacy relay may omit the email,
    and Apple only returns the name in the first authorization response, not in the
    ID token.
    """

    provider: str
    provider_id: str
    email: str | None = None
    name: str | None = None
