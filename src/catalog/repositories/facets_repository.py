"""Aggregation queries backing the per-category facet schema (option lists + counts)."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.catalog.models import Product, ProductCategory, ProductCoffee


class FacetsRepository:
    """Distinct-value counts and numeric bounds over the active products of one category."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_category(self, category_id: uuid.UUID) -> ProductCategory | None:
        category: ProductCategory | None = await self._db.scalar(
            select(ProductCategory)
            .where(ProductCategory.id == category_id)
            .options(joinedload(ProductCategory.product_type))
        )
        return category

    async def enum_counts(
        self, subtype: type[Any], column: Any, category_id: uuid.UUID
    ) -> list[tuple[str, int]]:
        """`(value, count)` for a subtype column, most frequent first; NULLs dropped."""
        stmt = (
            select(column, func.count())
            .select_from(Product)
            .join(subtype, subtype.id == Product.id)
            .where(Product.product_category_id == category_id, Product.is_active.is_(True))
            .group_by(column)
            .order_by(func.count().desc(), column.asc())
        )
        rows = await self._db.execute(stmt)
        return [(value, count) for value, count in rows.all() if value is not None]

    async def range_bounds(
        self, subtype: type[Any], column: Any, category_id: uuid.UUID
    ) -> tuple[int | None, int | None]:
        stmt = (
            select(func.min(column), func.max(column))
            .select_from(Product)
            .join(subtype, subtype.id == Product.id)
            .where(Product.product_category_id == category_id, Product.is_active.is_(True))
        )
        low, high = (await self._db.execute(stmt)).one()
        return low, high

    async def coffee_flavor_notes(self, category_id: uuid.UUID) -> list[dict[str, Any]]:
        """The raw multilingual flavor-notes objects of the category's active coffees."""
        stmt = (
            select(ProductCoffee.flavor_notes)
            .select_from(Product)
            .join(ProductCoffee, ProductCoffee.id == Product.id)
            .where(Product.product_category_id == category_id, Product.is_active.is_(True))
        )
        return [notes for notes in (await self._db.scalars(stmt)).all() if notes]

    async def acidity_counts(self, category_id: uuid.UUID) -> list[tuple[int, int]]:
        stmt = (
            select(ProductCoffee.acidity, func.count())
            .select_from(Product)
            .join(ProductCoffee, ProductCoffee.id == Product.id)
            .where(Product.product_category_id == category_id, Product.is_active.is_(True))
            .group_by(ProductCoffee.acidity)
        )
        return [(value, count) for value, count in (await self._db.execute(stmt)).all()]
