"""Shared S2S (service-to-service) credential check.

crew_shop is the verifier: it compares a per-environment shared service token (constant-time)
and records the on-behalf-of operator/role propagated by a trusted backend (e.g. crew_admin).
Each calling domain supplies its own ``forbidden`` error type (and audit logger) so error codes
stay domain-specific; only the security-critical token check lives here. A signed-JWT or
client-credentials scheme can replace this without touching the endpoints.
"""

from collections.abc import Callable
from dataclasses import dataclass
from hmac import compare_digest

from src.api.core.configs import settings
from src.api.exceptions import AppException


@dataclass(frozen=True, slots=True)
class ServiceCaller:
    """The acting operator behind an S2S call, for audit and optional enforcement."""

    operator: str
    role: str | None


def resolve_service_caller(
    service_token: str | None,
    acting_operator: str | None,
    acting_role: str | None,
    *,
    forbidden: Callable[[str], AppException],
) -> ServiceCaller:
    """Authorize the shared service credential and extract the acting operator.

    Raises ``forbidden(...)`` when the S2S API is unconfigured, the token is missing/wrong, or
    no acting operator is supplied (on-behalf-of is required for audit).
    """
    expected = settings.admin_service_token
    if not expected:
        raise forbidden("Admin API is not configured")
    if not service_token or not compare_digest(service_token, expected):
        raise forbidden("Invalid admin service credential")
    if not acting_operator:
        raise forbidden("Missing acting operator")
    return ServiceCaller(operator=acting_operator, role=acting_role)
