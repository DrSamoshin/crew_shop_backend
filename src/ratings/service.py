"""Rating aggregate recomputation.

The denormalized :class:`ProductRating` is rebuilt from the raw :class:`Rating` rows.
Mutations are flushed, not committed — the caller's unit of work commits.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.ratings.models.product_rating import (
    ProductRating,
    average_of,
    build_distribution,
)
from src.ratings.models.rating import Rating


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
