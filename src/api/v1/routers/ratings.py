"""Rating endpoints: write (PUT/DELETE) + public breakdown (GET), and the caller's My Ratings.

PUT/DELETE require auth and purchase verification; GET breakdown is public. The catalog read
API (`/v1/catalog/products`) is enriched separately with `user_rating` / `can_rate` when the
caller is signed in.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.auth.dependencies import require_auth
from src.ratings import service
from src.ratings.schemas import (
    MyRatingsListDTO,
    ProductRatingSummaryDTO,
    RateProductRequest,
    RatingBreakdownDTO,
)
from src.users.models import User

router = APIRouter(prefix="/products", tags=["ratings"])
me_router = APIRouter(prefix="/users/me", tags=["ratings"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserDep = Annotated[User, Depends(require_auth)]


@router.put(
    "/{product_id}/rating",
    response_model=ProductRatingSummaryDTO,
    summary="Create or update the caller's rating",
)
async def rate_product(
    product_id: uuid.UUID, payload: RateProductRequest, db: DbDep, user: UserDep
) -> ProductRatingSummaryDTO:
    return await service.set_rating(db, user.id, product_id, payload.rating)


@router.delete(
    "/{product_id}/rating",
    response_model=ProductRatingSummaryDTO,
    summary="Delete the caller's rating",
)
async def delete_my_rating(
    product_id: uuid.UUID, db: DbDep, user: UserDep
) -> ProductRatingSummaryDTO:
    return await service.delete_rating(db, user.id, product_id)


@router.get(
    "/{product_id}/rating",
    response_model=RatingBreakdownDTO,
    summary="Public rating breakdown (counts + percentages per star)",
)
async def get_rating_breakdown(product_id: uuid.UUID, db: DbDep) -> RatingBreakdownDTO:
    return await service.get_breakdown(db, product_id)


@me_router.get(
    "/ratings",
    response_model=MyRatingsListDTO,
    summary="List the caller's ratings (Account 'My Ratings')",
)
async def list_my_ratings(db: DbDep, user: UserDep) -> MyRatingsListDTO:
    return await service.list_user_ratings(db, user.id)
