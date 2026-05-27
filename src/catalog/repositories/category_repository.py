"""Category queries."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.catalog.models import Category


class CategoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_active(self) -> list[Category]:
        """All active categories, alphabetical."""
        result = await self._db.scalars(
            select(Category).where(Category.is_active.is_(True)).order_by(Category.name.asc())
        )
        return list(result.all())
