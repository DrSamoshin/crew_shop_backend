"""ProductCategory queries."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.catalog.models import ProductCategory


class ProductCategoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_active(self) -> list[ProductCategory]:
        """All active categories (with their product type), alphabetical."""
        result = await self._db.scalars(
            select(ProductCategory)
            .where(ProductCategory.is_active.is_(True))
            .options(joinedload(ProductCategory.product_type))
            .order_by(ProductCategory.name.asc())
        )
        return list(result.all())

    async def list_all(self) -> list[ProductCategory]:
        """Every category, active and inactive (with their product type), alphabetical."""
        result = await self._db.scalars(
            select(ProductCategory)
            .options(joinedload(ProductCategory.product_type))
            .order_by(ProductCategory.name.asc())
        )
        return list(result.all())
