"""Unit tests for auth cookie attributes."""

from starlette.responses import Response

from src.auth.cookies import CSRF_COOKIE, REFRESH_COOKIE, set_auth_cookies


def _set_cookie(response: Response, name: str) -> str:
    for key, value in response.raw_headers:
        if key == b"set-cookie" and value.decode().startswith(f"{name}="):
            return value.decode()
    raise AssertionError(f"no Set-Cookie for {name}")


def test_refresh_cookie_is_httponly_and_scoped() -> None:
    response = Response()
    set_auth_cookies(response, "refresh-value")
    refresh = _set_cookie(response, REFRESH_COOKIE)
    assert "Path=/v1/auth" in refresh
    assert "HttpOnly" in refresh


def test_csrf_cookie_is_root_path_and_js_readable() -> None:
    # The SPA at `/` must read csrf_token via document.cookie for the double-submit.
    response = Response()
    set_auth_cookies(response, "refresh-value")
    csrf = _set_cookie(response, CSRF_COOKIE)
    assert "Path=/" in csrf
    assert "Path=/v1/auth" not in csrf
    assert "HttpOnly" not in csrf
