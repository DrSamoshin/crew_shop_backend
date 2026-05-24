"""Centralized exception handlers producing standardized error responses."""

import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.exceptions import AppException


def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid.uuid4()))


def _build_error_response(
    request: Request,
    status_code: int,
    error_code: str,
    message: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "error_code": error_code,
                "status_code": status_code,
                "message": message,
                "request_id": _get_request_id(request),
            }
        },
    )


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return _build_error_response(request, exc.status_code, exc.error_code, exc.message)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    error_codes = {404: "ROUTE_NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
    return _build_error_response(
        request,
        exc.status_code,
        error_codes.get(exc.status_code, "HTTP_ERROR"),
        exc.detail if isinstance(exc.detail, str) else "Request failed",
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    first = errors[0] if errors else {}
    field = " -> ".join(str(loc) for loc in first.get("loc", []))
    message = str(first.get("msg", "Validation failed"))
    full = f"Validation failed: {field}: {message}" if field else message
    return _build_error_response(
        request, status.HTTP_422_UNPROCESSABLE_ENTITY, "VALIDATION_ERROR", full
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return _build_error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "INTERNAL_SERVER_ERROR",
        "Internal server error",
    )


def setup_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppException, app_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, generic_exception_handler)
