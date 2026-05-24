"""CORS middleware setup. Allowed origins come from settings, never hardcoded."""

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from src.api.core.configs import settings


def setup_cors(app: FastAPI) -> None:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=3600,
    )
