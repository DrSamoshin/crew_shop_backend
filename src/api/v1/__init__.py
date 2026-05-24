from fastapi import APIRouter

from src.api.v1.routers import auth_router, health_router

api_router = APIRouter(prefix="/v1")
api_router.include_router(health_router)
api_router.include_router(auth_router)

__all__ = ["api_router"]
