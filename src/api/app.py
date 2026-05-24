import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.core.configs import settings
from src.api.core.database import close_db
from src.api.exception_handlers import setup_exception_handlers
from src.api.middleware import setup_middlewares
from src.api.v1 import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    logger.info(f"FastAPI app started in '{settings.env}' environment")
    logger.info(f"Database URL: {settings.get_database_url_masked()}")
    yield
    logger.info("Closing database connections...")
    await close_db()
    logger.info("FastAPI app shutting down")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_title, version=settings.app_version, lifespan=lifespan)
    setup_exception_handlers(app)
    setup_middlewares(app)
    app.include_router(api_router)
    return app


fastapi_app = create_app()


__all__ = ["create_app", "fastapi_app"]
