"""Central place for configuring application middleware."""

from fastapi import FastAPI

from src.api.middleware.cors import setup_cors
from src.api.middleware.logging import setup_logging_middleware


def setup_middlewares(app: FastAPI) -> None:
    """Configure all middleware. CORS first (preflight), then request logging."""
    setup_cors(app)
    setup_logging_middleware(app)


__all__ = ["setup_middlewares"]
