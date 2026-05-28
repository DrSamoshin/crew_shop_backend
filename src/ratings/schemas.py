"""Rating request and response DTOs.

The numeric aggregate (``average_rating``) is serialized as a plain string ("4.5") to preserve
``Numeric(2,1)`` precision; the breakdown DTO carries per-star count + percentage.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, PlainSerializer

DecimalStr = Annotated[
    Decimal, PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json")
]


# --------------------------------------------------------------------- requests


class RateProductRequest(BaseModel):
    """The 1..5 range is enforced in the service so callers get ``RATING_INVALID_VALUE`` 400."""

    rating: int


# --------------------------------------------------------------------- responses


class ProductRatingSummaryDTO(BaseModel):
    """Returned by the rating PUT/DELETE endpoints."""

    product_id: uuid.UUID
    user_rating: int | None
    average_rating: DecimalStr | None
    total_ratings: int
    rating_distribution: dict[str, int]


class StarBreakdownDTO(BaseModel):
    count: int
    percentage: float


class RatingBreakdownDTO(BaseModel):
    """Public per-product rating breakdown (counts + percentages per star)."""

    product_id: uuid.UUID
    product_name: str
    average_rating: DecimalStr | None
    total_ratings: int
    rating_distribution: dict[str, StarBreakdownDTO]


class MyRatingDTO(BaseModel):
    """One of the caller's ratings; carries product name/image for the Account 'My Ratings'."""

    product_id: uuid.UUID
    product_name: str
    product_image_url: str | None
    rating: int
    updated_at: datetime


class MyRatingsListDTO(BaseModel):
    items: list[MyRatingDTO]
    total: int
