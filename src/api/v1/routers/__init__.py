from src.api.v1.routers.admin_catalog import router as admin_catalog_router
from src.api.v1.routers.admin_orders import router as admin_orders_router
from src.api.v1.routers.admin_points import router as admin_points_router
from src.api.v1.routers.auth import router as auth_router
from src.api.v1.routers.catalog import router as catalog_router
from src.api.v1.routers.health import router as health_router
from src.api.v1.routers.orders import router as orders_router
from src.api.v1.routers.payment_methods import router as payment_methods_router
from src.api.v1.routers.payments import router as payments_router
from src.api.v1.routers.points import router as points_router
from src.api.v1.routers.ratings import me_router as my_ratings_router
from src.api.v1.routers.ratings import router as ratings_router
from src.api.v1.routers.subscriptions import router as subscriptions_router
from src.api.v1.routers.users import router as users_router

__all__ = [
    "admin_catalog_router",
    "admin_orders_router",
    "admin_points_router",
    "auth_router",
    "catalog_router",
    "health_router",
    "my_ratings_router",
    "orders_router",
    "payment_methods_router",
    "payments_router",
    "points_router",
    "ratings_router",
    "subscriptions_router",
    "users_router",
]
