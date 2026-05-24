"""Request logging middleware.

Generates a request ID for tracing, logs each completed request with metadata,
and exposes X-Request-ID / X-Process-Time response headers.
"""

import logging
import time
import uuid

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log requests, attach request_id to request.state, skip noisy paths."""

    SKIP_PATHS = {"/metrics", "/docs", "/redoc", "/openapi.json"}

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in self.SKIP_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start_time = time.time()

        response = await call_next(request)

        duration = time.time() - start_time
        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration * 1000, 2),
            },
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{duration:.4f}"
        return response


def setup_logging_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestLoggingMiddleware)
