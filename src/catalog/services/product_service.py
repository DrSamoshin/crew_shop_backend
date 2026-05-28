"""Product service: orchestrates the repository and maps ORM rows to response DTOs."""

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.catalog.exceptions import ProductNotFoundError
from src.catalog.models import (
    ProductAccessories,
    ProductCoffee,
    ProductConsumables,
    ProductEquipment,
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
        "category_id": product.category_id,
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
        rows, total = await self._repo.list_products(filters, sort, limit, offset)
        items = [_to_product_dto(row) for row in rows]
        await self._enrich(items, user_id)
        return ProductListDTO(items=items, total=total, limit=limit, offset=offset)

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
