"""Category service."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.catalog.repositories.category_repository import CategoryRepository
from src.catalog.schemas.catalog import CategoryDTO, CategoryListDTO


class CategoryService:
    def __init__(self, db: AsyncSession) -> None:
        self._repo = CategoryRepository(db)

    async def list_categories(self) -> CategoryListDTO:
        categories = await self._repo.list_active()
        items = [
            CategoryDTO(id=category.id, name=category.name, description=category.description)
            for category in categories
        ]
        return CategoryListDTO(items=items, total=len(items))
