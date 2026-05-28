"""S2S gate for the points admin API.

Same shared-secret scheme as the catalog/orders admin gates: the token check lives in
:mod:`src.api.core.service_auth`; here it is wired to the ``POINT_ADMIN_FORBIDDEN`` error and
the points audit log.
"""

import logging
from typing import Annotated

from fastapi import Header

from src.api.core.configs import settings
from src.api.core.service_auth import ServiceCaller, resolve_service_caller
from src.points.exceptions import PointAdminForbiddenError

__all__ = ["ServiceCaller", "audit", "require_service_caller"]

_audit = logging.getLogger("src.points.admin.audit")


async def require_service_caller(
    x_service_token: Annotated[str | None, Header()] = None,
    x_acting_operator: Annotated[str | None, Header()] = None,
    x_acting_role: Annotated[str | None, Header()] = None,
) -> ServiceCaller:
    """Authorize the crew_admin service credential and extract the acting operator.

    Rejects with ``POINT_ADMIN_FORBIDDEN`` when the admin API is unconfigured, the token is
    missing/wrong, or no acting operator is supplied (on-behalf-of is required for audit).
    """
    return resolve_service_caller(
        x_service_token, x_acting_operator, x_acting_role, forbidden=PointAdminForbiddenError
    )


def audit(caller: ServiceCaller, action: str, target: str) -> None:
    """Emit a structured audit record for a successful admin write."""
    _audit.info(
        "admin point op: %s %s",
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
