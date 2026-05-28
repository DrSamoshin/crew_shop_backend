"""Ratings service: aggregate recompute, write operations, purchase verification, enrichment.

Mutations are flushed, not committed — the caller's unit of work commits.
``recalculate_product_rating`` rebuilds the denormalized aggregate from the raw ``Rating`` rows;
``set_rating`` / ``delete_rating`` are the user-facing upsert/remove that drive it.
"""

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.catalog.exceptions import ProductNotFoundError
from src.catalog.models import Product
from src.orders.enums import OrderStatus
from src.orders.models import Order, OrderProduct
from src.ratings.exceptions import (
    RatingInvalidValueError,
    RatingNotFoundError,
    RatingNotPurchasedError,
)
from src.ratings.models.product_rating import (
    ProductRating,
    average_of,
    build_distribution,
    empty_distribution,
)
from src.ratings.models.rating import Rating
from src.ratings.schemas import (
    MyRatingDTO,
    MyRatingsListDTO,
    ProductRatingSummaryDTO,
    RatingBreakdownDTO,
    StarBreakdownDTO,
)

# Purchase verification: a rating requires a completed order containing the product.
_PURCHASED_STATUS = OrderStatus.COMPLETED.value


# ------------------------------------------------------------------- aggregate


async def recalculate_product_rating(
    db: AsyncSession, product_id: uuid.UUID
) -> ProductRating | None:
    """Rebuild a product's aggregate from its ratings. Removes the row if no ratings remain."""
    scores: list[int] = list(
        await db.scalars(select(Rating.rating).where(Rating.product_id == product_id))
    )
    existing = await db.scalar(select(ProductRating).where(ProductRating.product_id == product_id))

    if not scores:
        if existing is not None:
            await db.delete(existing)
            await db.flush()
        return None

    average = average_of(scores)
    distribution = build_distribution(scores)
    if existing is None:
        existing = ProductRating(
            product_id=product_id,
            average_rating=average,
            total_ratings=len(scores),
            distribution=distribution,
        )
        db.add(existing)
    else:
        existing.average_rating = average
        existing.total_ratings = len(scores)
        existing.distribution = distribution
    await db.flush()
    return existing


# ---------------------------------------------------------- purchase verification


async def can_user_rate_product(
    db: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID
) -> bool:
    """``True`` iff the user has a completed order containing the product."""
    found = await db.scalar(
        select(OrderProduct.id)
        .join(Order, Order.id == OrderProduct.order_id)
        .where(
            Order.user_id == user_id,
            Order.status == _PURCHASED_STATUS,
            OrderProduct.product_id == product_id,
        )
        .limit(1)
    )
    return found is not None


async def get_purchased_product_ids(
    db: AsyncSession, user_id: uuid.UUID, product_ids: Iterable[uuid.UUID]
) -> set[uuid.UUID]:
    """Subset of ``product_ids`` the user has purchased (one query, for catalog enrichment)."""
    ids = list(product_ids)
    if not ids:
        return set()
    rows = await db.scalars(
        select(OrderProduct.product_id)
        .distinct()
        .join(Order, Order.id == OrderProduct.order_id)
        .where(
            Order.user_id == user_id,
            Order.status == _PURCHASED_STATUS,
            OrderProduct.product_id.in_(ids),
        )
    )
    return set(rows)


async def get_user_ratings_map(
    db: AsyncSession, user_id: uuid.UUID, product_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Caller's ratings for the given product ids (one query, for catalog enrichment)."""
    ids = list(product_ids)
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(Rating.product_id, Rating.rating).where(
                Rating.user_id == user_id, Rating.product_id.in_(ids)
            )
        )
    ).all()
    return {pid: score for pid, score in rows}


# ------------------------------------------------------------------ writes / reads


async def _require_product(db: AsyncSession, product_id: uuid.UUID) -> Product:
    product = await db.get(Product, product_id)
    if product is None:
        raise ProductNotFoundError(str(product_id))
    return product


def _validate_rating(value: int) -> None:
    if not 1 <= value <= 5:
        raise RatingInvalidValueError()


def _summary(
    product_id: uuid.UUID, user_rating: int | None, aggregate: ProductRating | None
) -> ProductRatingSummaryDTO:
    if aggregate is None:
        return ProductRatingSummaryDTO(
            product_id=product_id,
            user_rating=user_rating,
            average_rating=None,
            total_ratings=0,
            rating_distribution=empty_distribution(),
        )
    return ProductRatingSummaryDTO(
        product_id=product_id,
        user_rating=user_rating,
        average_rating=aggregate.average_rating,
        total_ratings=aggregate.total_ratings,
        rating_distribution=dict(aggregate.distribution),
    )


async def set_rating(
    db: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID, rating: int
) -> ProductRatingSummaryDTO:
    """Upsert the caller's 1-5 star rating after purchase verification; recompute the aggregate."""
    _validate_rating(rating)
    await _require_product(db, product_id)
    if not await can_user_rate_product(db, user_id, product_id):
        raise RatingNotPurchasedError(str(product_id))

    existing = await db.scalar(
        select(Rating).where(Rating.product_id == product_id, Rating.user_id == user_id)
    )
    if existing is None:
        db.add(Rating(product_id=product_id, user_id=user_id, rating=rating))
    else:
        existing.rating = rating
    await db.flush()
    aggregate = await recalculate_product_rating(db, product_id)
    return _summary(product_id, rating, aggregate)


async def delete_rating(
    db: AsyncSession, user_id: uuid.UUID, product_id: uuid.UUID
) -> ProductRatingSummaryDTO:
    """Remove the caller's rating and recompute the aggregate."""
    existing = await db.scalar(
        select(Rating).where(Rating.product_id == product_id, Rating.user_id == user_id)
    )
    if existing is None:
        raise RatingNotFoundError(str(product_id))
    await db.delete(existing)
    await db.flush()
    aggregate = await recalculate_product_rating(db, product_id)
    return _summary(product_id, None, aggregate)


async def get_breakdown(db: AsyncSession, product_id: uuid.UUID) -> RatingBreakdownDTO:
    """Per-star count and percentage for the product (public; 404 if the product is missing)."""
    product = await _require_product(db, product_id)
    aggregate = await db.scalar(select(ProductRating).where(ProductRating.product_id == product_id))
    if aggregate is None:
        empty = {str(star): StarBreakdownDTO(count=0, percentage=0.0) for star in range(1, 6)}
        return RatingBreakdownDTO(
            product_id=product_id,
            product_name=product.name,
            average_rating=None,
            total_ratings=0,
            rating_distribution=empty,
        )

    total = aggregate.total_ratings
    breakdown = {
        str(star): StarBreakdownDTO(
            count=aggregate.distribution.get(str(star), 0),
            percentage=round(aggregate.distribution.get(str(star), 0) / total * 100, 1),
        )
        for star in range(1, 6)
    }
    return RatingBreakdownDTO(
        product_id=product_id,
        product_name=product.name,
        average_rating=aggregate.average_rating,
        total_ratings=total,
        rating_distribution=breakdown,
    )


async def list_user_ratings(db: AsyncSession, user_id: uuid.UUID) -> MyRatingsListDTO:
    """The caller's ratings, newest-updated first, with the product name/image for display."""
    rows = (
        await db.execute(
            select(Rating, Product)
            .join(Product, Product.id == Rating.product_id)
            .where(Rating.user_id == user_id)
            .order_by(Rating.updated_at.desc(), Rating.id.desc())
        )
    ).all()
    items = [
        MyRatingDTO(
            product_id=product.id,
            product_name=product.name,
            product_image_url=product.image_url,
            rating=rating.rating,
            updated_at=rating.updated_at,
        )
        for (rating, product) in rows
    ]
    return MyRatingsListDTO(items=items, total=len(items))
