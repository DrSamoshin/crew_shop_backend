from fastapi import APIRouter

from src.api.v1.routers import (
    admin_catalog_router,
    admin_orders_router,
    admin_points_router,
    auth_router,
    catalog_router,
    health_router,
    my_ratings_router,
    orders_router,
    payments_router,
    points_router,
    ratings_router,
    subscriptions_router,
    users_router,
)

api_router = APIRouter(prefix="/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(catalog_router)
api_router.include_router(admin_catalog_router)
api_router.include_router(orders_router)
api_router.include_router(admin_orders_router)
api_router.include_router(users_router)
api_router.include_router(ratings_router)
api_router.include_router(my_ratings_router)
api_router.include_router(points_router)
api_router.include_router(admin_points_router)
api_router.include_router(subscriptions_router)
api_router.include_router(payments_router)

__all__ = ["api_router"]
