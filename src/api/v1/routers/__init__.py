from src.api.v1.routers.auth import router as auth_router
from src.api.v1.routers.catalog import router as catalog_router
from src.api.v1.routers.health import router as health_router

__all__ = ["auth_router", "catalog_router", "health_router"]
