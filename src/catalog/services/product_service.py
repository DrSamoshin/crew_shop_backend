"""Product service: orchestrates the repository and maps ORM rows to response DTOs."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.catalog.enums import ProductTypeName
from src.catalog.exceptions import CatalogInvalidFilterError, ProductNotFoundError
from src.catalog.models import (
    ProductAccessories,
    ProductCategory,
    ProductCoffee,
    ProductConsumables,
    ProductEquipment,
    ProductType,
)
from src.catalog.repositories.product_repository import ProductRepository, ProductRow
from src.catalog.schemas.catalog import (
    AccessoryAttributesDTO,
    CoffeeAttributesDTO,
    ConsumableAttributesDTO,
    EquipmentAttributesDTO,
    ProductDetailDTO,
    ProductDTO,
    ProductFilters,
    ProductListDTO,
    SortOption,
)
from src.ratings import service as ratings_service

# Each per-type facet group requires its product_type; material is valid for any of the three.
_MATERIAL_TYPES = frozenset(
    {ProductTypeName.EQUIPMENT, ProductTypeName.ACCESSORIES, ProductTypeName.CONSUMABLES}
)


def _coffee_dto(coffee: ProductCoffee) -> CoffeeAttributesDTO:
    return CoffeeAttributesDTO(
        region=coffee.region,
        roast_level=coffee.roast_level,
        processing=coffee.processing,
        acidity=coffee.acidity,
        body=coffee.body,
        sweetness=coffee.sweetness,
        altitude=coffee.altitude,
        flavor_notes=coffee.flavor_notes,
    )


def _equipment_dto(equipment: ProductEquipment) -> EquipmentAttributesDTO:
    return EquipmentAttributesDTO(
        equipment_type=equipment.equipment_type,
        power_watts=equipment.power_watts,
        warranty_months=equipment.warranty_months,
        width_cm=equipment.width_cm,
        height_cm=equipment.height_cm,
        depth_cm=equipment.depth_cm,
        weight_kg=equipment.weight_kg,
        material=equipment.material,
        other_options=equipment.other_options,
    )


def _accessory_dto(accessory: ProductAccessories) -> AccessoryAttributesDTO:
    return AccessoryAttributesDTO(
        accessory_type=accessory.accessory_type,
        material=accessory.material,
        other_options=accessory.other_options,
    )


def _consumable_dto(consumable: ProductConsumables) -> ConsumableAttributesDTO:
    return ConsumableAttributesDTO(
        consumable_type=consumable.consumable_type,
        quantity_per_pack=consumable.quantity_per_pack,
        unit_description=consumable.unit_description,
        material=consumable.material,
        expiry_months=consumable.expiry_months,
        storage_conditions=consumable.storage_conditions,
        other_options=consumable.other_options,
    )


def _product_kwargs(row: ProductRow) -> dict[str, Any]:
    product, aggregate = row
    return {
        "id": product.id,
        "product_category_id": product.product_category_id,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "currency": product.currency,
        "product_type": product.product_type.name,
        "is_active": product.is_active,
        "rating": float(aggregate.average_rating) if aggregate else None,
        "rating_count": aggregate.total_ratings if aggregate else 0,
        "coffee": _coffee_dto(product.coffee) if product.coffee else None,
        "equipment": _equipment_dto(product.equipment) if product.equipment else None,
        "accessory": _accessory_dto(product.accessory) if product.accessory else None,
        "consumable": _consumable_dto(product.consumable) if product.consumable else None,
    }


def _to_product_dto(row: ProductRow) -> ProductDTO:
    return ProductDTO(**_product_kwargs(row))


def _to_detail_dto(row: ProductRow) -> ProductDetailDTO:
    product, aggregate = row
    return ProductDetailDTO(
        **_product_kwargs(row),
        category_name=product.category.name,
        rating_distribution=aggregate.distribution if aggregate else None,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


class ProductService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = ProductRepository(db)

    async def list_products(
        self,
        filters: ProductFilters,
        sort: SortOption,
        limit: int,
        offset: int,
        user_id: uuid.UUID | None = None,
    ) -> ProductListDTO:
        product_type = await self._resolve_scope_type(filters)
        self._validate_type_facets(filters, product_type)
        rows, total = await self._repo.list_products(filters, sort, limit, offset, product_type)
        items = [_to_product_dto(row) for row in rows]
        await self._enrich(items, user_id)
        return ProductListDTO(items=items, total=total, limit=limit, offset=offset)

    async def _resolve_scope_type(self, filters: ProductFilters) -> ProductTypeName | None:
        """Resolve the scoped category to its product type (None when unscoped)."""
        if filters.product_category_id is None:
            return None
        name = await self._db.scalar(
            select(ProductType.name)
            .join(ProductCategory, ProductCategory.product_type_id == ProductType.id)
            .where(ProductCategory.id == filters.product_category_id)
        )
        if name is None:
            raise CatalogInvalidFilterError("product_category_id", str(filters.product_category_id))
        return ProductTypeName(name)

    @staticmethod
    def _validate_type_facets(
        filters: ProductFilters, product_type: ProductTypeName | None
    ) -> None:
        """A per-type facet is only valid when the scoped category resolves to that type."""
        if filters.has_equipment_filter and product_type is not ProductTypeName.EQUIPMENT:
            raise CatalogInvalidFilterError("equipment_type", "requires an equipment category")
        if filters.has_accessory_filter and product_type is not ProductTypeName.ACCESSORIES:
            raise CatalogInvalidFilterError("accessory_type", "requires an accessory category")
        if filters.has_consumable_filter and product_type is not ProductTypeName.CONSUMABLES:
            raise CatalogInvalidFilterError("consumable_type", "requires a consumable category")
        if filters.has_material_filter and product_type not in _MATERIAL_TYPES:
            raise CatalogInvalidFilterError("material", "requires a non-coffee category")

    async def get_product(
        self, product_id: uuid.UUID, user_id: uuid.UUID | None = None
    ) -> ProductDetailDTO:
        row = await self._repo.get(product_id)
        if row is None:
            raise ProductNotFoundError(str(product_id))
        dto = _to_detail_dto(row)
        await self._enrich([dto], user_id)
        return dto

    async def search_products(
        self, query: str, limit: int, offset: int, user_id: uuid.UUID | None = None
    ) -> ProductListDTO:
        rows, total = await self._repo.search(query, limit, offset)
        items = [_to_product_dto(row) for row in rows]
        await self._enrich(items, user_id)
        return ProductListDTO(items=items, total=total, limit=limit, offset=offset)

    async def _enrich(self, dtos: Sequence[ProductDTO], user_id: uuid.UUID | None) -> None:
        """Set ``user_rating`` / ``can_rate`` per DTO when the caller is authenticated."""
        if user_id is None or not dtos:
            return
        product_ids = [dto.id for dto in dtos]
        ratings_map = await ratings_service.get_user_ratings_map(self._db, user_id, product_ids)
        purchased = await ratings_service.get_purchased_product_ids(self._db, user_id, product_ids)
        for dto in dtos:
            dto.user_rating = ratings_map.get(dto.id)
            dto.can_rate = dto.id in purchased
