"""S2S gate for the catalog admin API.

crew_shop is the verifier: it checks a per-environment shared service token (constant-time)
and records the on-behalf-of operator/role propagated by the crew_admin backend. There is no
central IdP yet; a signed-JWT or client-credentials scheme can replace this without touching
the endpoints.
"""

import hmac
import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header

from src.api.core.configs import settings
from src.catalog.exceptions import AdminForbiddenError

_audit = logging.getLogger("src.catalog.admin.audit")


@dataclass(frozen=True, slots=True)
class ServiceCaller:
    """The acting operator behind an S2S admin call, for audit and optional enforcement."""

    operator: str
    role: str | None


async def require_service_caller(
    x_service_token: Annotated[str | None, Header()] = None,
    x_acting_operator: Annotated[str | None, Header()] = None,
    x_acting_role: Annotated[str | None, Header()] = None,
) -> ServiceCaller:
    """Authorize the crew_admin service credential and extract the acting operator.

    Rejects with ``CATALOG_ADMIN_FORBIDDEN`` when the admin API is unconfigured, the token is
    missing/wrong, or no acting operator is supplied (on-behalf-of is required for audit).
    """
    expected = settings.admin_service_token
    if not expected:
        raise AdminForbiddenError("Admin API is not configured")
    if not x_service_token or not hmac.compare_digest(x_service_token, expected):
        raise AdminForbiddenError()
    if not x_acting_operator:
        raise AdminForbiddenError("Missing acting operator")
    return ServiceCaller(operator=x_acting_operator, role=x_acting_role)


def audit(caller: ServiceCaller, action: str, target: str) -> None:
    """Emit a structured audit record for a successful admin write."""
    _audit.info(
        "admin write: %s %s",
        action,
        target,
        extra={
            "audit": True,
            "operator": caller.operator,
            "role": caller.role,
            "environment": settings.env,
            "action": action,
            "target": target,
        },
    )
