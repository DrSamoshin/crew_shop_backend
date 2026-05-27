from src.api.v1.routers.admin_catalog import router as admin_catalog_router
from src.api.v1.routers.admin_orders import router as admin_orders_router
from src.api.v1.routers.auth import router as auth_router
from src.api.v1.routers.catalog import router as catalog_router
from src.api.v1.routers.health import router as health_router
from src.api.v1.routers.orders import router as orders_router
from src.api.v1.routers.users import router as users_router

__all__ = [
    "admin_catalog_router",
    "admin_orders_router",
    "auth_router",
    "catalog_router",
    "health_router",
    "orders_router",
    "users_router",
]
