"""Refresh-cookie handling and double-submit CSRF protection.

The refresh token rides in an httpOnly Secure SameSite cookie scoped to ``/v1/auth``.
A companion non-httpOnly ``csrf_token`` cookie is echoed back by the client in the
``X-CSRF-Token`` header on the cookie-authenticated refresh/logout calls; the two
must match (double-submit), which a cross-site attacker cannot arrange.
"""

import secrets
from typing import Literal

from fastapi import Request, Response

from src.api.core.configs import settings
from src.auth.exceptions import CsrfValidationError

REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
COOKIE_PATH = "/v1/auth"
_SAMESITE: Literal["lax", "strict", "none"] = "lax"


def _secure() -> bool:
    # Secure breaks plain-http local dev; enable it everywhere except dev.
    return not settings.is_dev


def set_auth_cookies(response: Response, refresh_token: str) -> None:
    """Set the refresh and CSRF cookies (called on login / register / refresh)."""
    max_age = settings.refresh_token_ttl
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=max_age,
        httponly=True,
        secure=_secure(),
        samesite=_SAMESITE,
        path=COOKIE_PATH,
    )
    response.set_cookie(
        CSRF_COOKIE,
        secrets.token_urlsafe(32),
        max_age=max_age,
        httponly=False,
        secure=_secure(),
        samesite=_SAMESITE,
        path=COOKIE_PATH,
    )


def clear_auth_cookies(response: Response) -> None:
    """Clear the refresh and CSRF cookies (called on logout)."""
    response.delete_cookie(REFRESH_COOKIE, path=COOKIE_PATH)
    response.delete_cookie(CSRF_COOKIE, path=COOKIE_PATH)


async def require_csrf(request: Request) -> None:
    """Reject the request unless the CSRF cookie and header are present and equal."""
    cookie = request.cookies.get(CSRF_COOKIE)
    header = request.headers.get(CSRF_HEADER)
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise CsrfValidationError()
