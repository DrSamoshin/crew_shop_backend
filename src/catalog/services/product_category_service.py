"""ProductCategory service."""

from sqlalchemy.ext.asyncio import AsyncSession

from src.catalog.repositories.product_category_repository import ProductCategoryRepository
from src.catalog.schemas.catalog import ProductCategoryDTO, ProductCategoryListDTO


class ProductCategoryService:
    def __init__(self, db: AsyncSession) -> None:
        self._repo = ProductCategoryRepository(db)

    async def list_categories(self) -> ProductCategoryListDTO:
        categories = await self._repo.list_active()
        items = [
            ProductCategoryDTO(
                id=category.id,
                name=category.name,
                description=category.description,
                product_type=category.product_type.name,
            )
            for category in categories
        ]
        return ProductCategoryListDTO(items=items, total=len(items))
