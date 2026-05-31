"""Product queries: filtered listing, by-id detail, and name search.

Each read also left-joins the read-only :class:`ProductRating` aggregate and eager-loads
the product's type-specific attributes. Filtering stays in SQL on indexed columns.
"""

import uuid

from sqlalchemy import ColumnExpressionArgument, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.interfaces import ORMOption

from src.catalog.enums import ProductTypeName
from src.catalog.models import (
    Product,
    ProductAccessories,
    ProductCoffee,
    ProductConsumables,
    ProductEquipment,
)
from src.catalog.schemas.catalog import AcidityBucket, ProductFilters, SortOption
from src.ratings.models import ProductRating

# A product paired with its rating aggregate (None when the product has no ratings).
ProductRow = tuple[Product, ProductRating | None]

_ACIDITY_RANGES: dict[AcidityBucket, tuple[int, int]] = {
    AcidityBucket.SOFT: (1, 2),
    AcidityBucket.BALANCED: (3, 3),
    AcidityBucket.BRIGHT: (4, 5),
}


def _eager_options() -> tuple[ORMOption, ...]:
    """Eager-load the category, type, and every attribute subtype.

    Built lazily (not at import): constructing loader options triggers mapper configuration,
    which must happen at request time once all model modules are registered.
    """
    return (
        selectinload(Product.coffee),
        selectinload(Product.equipment),
        selectinload(Product.accessory),
        selectinload(Product.consumable),
        joinedload(Product.category),
        joinedload(Product.product_type),
    )


def _order_by(sort: SortOption) -> tuple[ColumnExpressionArgument[object], ...]:
    if sort is SortOption.PRICE_ASC:
        return (Product.price.asc(), Product.id.asc())
    if sort is SortOption.PRICE_DESC:
        return (Product.price.desc(), Product.id.asc())
    return (Product.created_at.desc(), Product.id.desc())


def _escape_like(term: str) -> str:
    """Escape LIKE wildcards so user input is matched literally."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ProductRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def _apply_filters(
        self,
        stmt: Select[tuple[Product]],
        filters: ProductFilters,
        product_type: ProductTypeName | None,
    ) -> Select[tuple[Product]]:
        stmt = stmt.where(Product.is_active.is_(True))
        if filters.product_category_id is not None:
            stmt = stmt.where(Product.product_category_id == filters.product_category_id)
        if filters.price_min is not None:
            stmt = stmt.where(Product.price >= filters.price_min)
        if filters.price_max is not None:
            stmt = stmt.where(Product.price <= filters.price_max)
        if filters.min_rating is not None:
            # IN-subquery (not a join) keeps the rating aggregate's outer join in _rows intact.
            stmt = stmt.where(
                Product.id.in_(
                    select(ProductRating.product_id).where(
                        ProductRating.average_rating >= filters.min_rating
                    )
                )
            )
        stmt = self._apply_coffee_filters(stmt, filters)
        stmt = self._apply_type_filters(stmt, filters, product_type)
        return stmt

    def _apply_coffee_filters(
        self, stmt: Select[tuple[Product]], filters: ProductFilters
    ) -> Select[tuple[Product]]:
        if not filters.has_coffee_filter:
            return stmt
        stmt = stmt.join(ProductCoffee, ProductCoffee.id == Product.id)
        if filters.flavor_notes:
            stmt = stmt.where(
                or_(
                    *[
                        ProductCoffee.flavor_notes["keys"].contains([key])
                        for key in filters.flavor_notes
                    ]
                )
            )
        if filters.region:
            stmt = stmt.where(ProductCoffee.region.in_(filters.region))
        if filters.roast_level:
            stmt = stmt.where(ProductCoffee.roast_level.in_(filters.roast_level))
        if filters.processing:
            stmt = stmt.where(ProductCoffee.processing.in_(filters.processing))
        if filters.acidity is not None:
            low, high = _ACIDITY_RANGES[filters.acidity]
            stmt = stmt.where(ProductCoffee.acidity.between(low, high))
        if filters.body_min is not None:
            stmt = stmt.where(ProductCoffee.body >= filters.body_min)
        if filters.body_max is not None:
            stmt = stmt.where(ProductCoffee.body <= filters.body_max)
        if filters.sweetness_min is not None:
            stmt = stmt.where(ProductCoffee.sweetness >= filters.sweetness_min)
        if filters.sweetness_max is not None:
            stmt = stmt.where(ProductCoffee.sweetness <= filters.sweetness_max)
        if filters.altitude_min is not None:
            stmt = stmt.where(ProductCoffee.altitude >= filters.altitude_min)
        if filters.altitude_max is not None:
            stmt = stmt.where(ProductCoffee.altitude <= filters.altitude_max)
        return stmt

    def _apply_type_filters(
        self,
        stmt: Select[tuple[Product]],
        filters: ProductFilters,
        product_type: ProductTypeName | None,
    ) -> Select[tuple[Product]]:
        """Apply equipment/accessory/consumable facets. The service guarantees these are set
        only when the scoped category resolves to the matching type, so ``material`` routes to
        that type's subtype table."""
        if product_type is ProductTypeName.EQUIPMENT and (
            filters.has_equipment_filter or filters.has_material_filter
        ):
            stmt = stmt.join(ProductEquipment, ProductEquipment.id == Product.id)
            if filters.equipment_type:
                stmt = stmt.where(ProductEquipment.equipment_type.in_(filters.equipment_type))
            if filters.power_min is not None:
                stmt = stmt.where(ProductEquipment.power_watts >= filters.power_min)
            if filters.power_max is not None:
                stmt = stmt.where(ProductEquipment.power_watts <= filters.power_max)
            if filters.warranty_min is not None:
                stmt = stmt.where(ProductEquipment.warranty_months >= filters.warranty_min)
            if filters.material:
                stmt = stmt.where(func.lower(ProductEquipment.material).in_(filters.material))
        elif product_type is ProductTypeName.ACCESSORIES and (
            filters.has_accessory_filter or filters.has_material_filter
        ):
            stmt = stmt.join(ProductAccessories, ProductAccessories.id == Product.id)
            if filters.accessory_type:
                stmt = stmt.where(ProductAccessories.accessory_type.in_(filters.accessory_type))
            if filters.material:
                stmt = stmt.where(func.lower(ProductAccessories.material).in_(filters.material))
        elif product_type is ProductTypeName.CONSUMABLES and (
            filters.has_consumable_filter or filters.has_material_filter
        ):
            stmt = stmt.join(ProductConsumables, ProductConsumables.id == Product.id)
            if filters.consumable_type:
                stmt = stmt.where(ProductConsumables.consumable_type.in_(filters.consumable_type))
            if filters.pack_min is not None:
                stmt = stmt.where(ProductConsumables.quantity_per_pack >= filters.pack_min)
            if filters.pack_max is not None:
                stmt = stmt.where(ProductConsumables.quantity_per_pack <= filters.pack_max)
            if filters.material:
                stmt = stmt.where(func.lower(ProductConsumables.material).in_(filters.material))
        return stmt

    async def _count(self, base: Select[tuple[Product]]) -> int:
        total = await self._db.scalar(select(func.count()).select_from(base.subquery()))
        return total or 0

    async def _rows(
        self,
        base: Select[tuple[Product]],
        order_by: tuple[ColumnExpressionArgument[object], ...],
        limit: int,
        offset: int,
    ) -> list[ProductRow]:
        stmt = (
            base.add_columns(ProductRating)
            .outerjoin(ProductRating, ProductRating.product_id == Product.id)
            .options(*_eager_options())
            .order_by(*order_by)
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        return [(row[0], row[1]) for row in result.unique().all()]

    async def list_products(
        self,
        filters: ProductFilters,
        sort: SortOption,
        limit: int,
        offset: int,
        product_type: ProductTypeName | None = None,
    ) -> tuple[list[ProductRow], int]:
        base = self._apply_filters(select(Product), filters, product_type)
        total = await self._count(base)
        rows = await self._rows(base, _order_by(sort), limit, offset)
        return rows, total

    async def get(self, product_id: uuid.UUID) -> ProductRow | None:
        stmt = (
            select(Product, ProductRating)
            .outerjoin(ProductRating, ProductRating.product_id == Product.id)
            .where(Product.id == product_id)
            .options(*_eager_options())
            # Read-after-write: refresh relationships on any instance already in the session.
            .execution_options(populate_existing=True)
        )
        row = (await self._db.execute(stmt)).unique().one_or_none()
        return (row[0], row[1]) if row is not None else None

    async def search(self, query: str, limit: int, offset: int) -> tuple[list[ProductRow], int]:
        pattern = f"%{_escape_like(query)}%"
        base = select(Product).where(
            Product.is_active.is_(True), Product.name.ilike(pattern, escape="\\")
        )
        total = await self._count(base)
        rows = await self._rows(base, (Product.name.asc(), Product.id.asc()), limit, offset)
        return rows, total
