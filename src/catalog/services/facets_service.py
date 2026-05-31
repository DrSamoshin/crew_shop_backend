"""Builds the dynamic filter schema for one category.

Most facet values (region, material, roast_level, ...) are free strings rather than enums, so
their option lists and counts are derived from the category's data here rather than hardcoded.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.catalog.enums import ProductTypeName
from src.catalog.exceptions import ProductCategoryNotFoundError
from src.catalog.models import (
    ProductAccessories,
    ProductCoffee,
    ProductConsumables,
    ProductEquipment,
)
from src.catalog.repositories.facets_repository import FacetsRepository
from src.catalog.schemas.catalog import CategoryFacetsDTO, FacetDTO, FacetOptionDTO

_ACIDITY_LABELS = {"soft": "Soft", "balanced": "Balanced", "bright": "Bright"}


def _label(value: str) -> str:
    return value.replace("-", " ").replace("_", " ").title()


class FacetsService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = FacetsRepository(db)

    async def get_facets(self, category_id: uuid.UUID) -> CategoryFacetsDTO:
        category = await self._repo.get_category(category_id)
        if category is None:
            raise ProductCategoryNotFoundError(str(category_id))
        product_type = ProductTypeName(category.product_type.name)
        facets = await self._facets_for(product_type, category_id)
        return CategoryFacetsDTO(
            product_category_id=category_id,
            product_type=product_type.value,
            facets=facets,
        )

    async def _facets_for(
        self, product_type: ProductTypeName, category_id: uuid.UUID
    ) -> list[FacetDTO]:
        if product_type is ProductTypeName.COFFEE:
            return await self._coffee_facets(category_id)
        if product_type is ProductTypeName.EQUIPMENT:
            return await self._equipment_facets(category_id)
        if product_type is ProductTypeName.ACCESSORIES:
            return await self._accessory_facets(category_id)
        return await self._consumable_facets(category_id)

    async def _enum_facet(
        self,
        key: str,
        label: str,
        kind: str,
        subtype: type[Any],
        column: Any,
        category_id: uuid.UUID,
    ) -> FacetDTO:
        counts = await self._repo.enum_counts(subtype, column, category_id)
        options = [FacetOptionDTO(value=v, label=_label(v), count=c) for v, c in counts]
        return FacetDTO(key=key, label=label, kind=kind, options=options)

    async def _range_facet(
        self, key: str, label: str, subtype: type[Any], column: Any, category_id: uuid.UUID
    ) -> FacetDTO:
        low, high = await self._repo.range_bounds(subtype, column, category_id)
        return FacetDTO(key=key, label=label, kind="range", min=low, max=high)

    async def _coffee_facets(self, category_id: uuid.UUID) -> list[FacetDTO]:
        return [
            await self._flavor_facet(category_id),
            await self._acidity_facet(category_id),
            await self._enum_facet(
                "region", "Region", "multi", ProductCoffee, ProductCoffee.region, category_id
            ),
            await self._enum_facet(
                "roast_level",
                "Roast level",
                "enum",
                ProductCoffee,
                ProductCoffee.roast_level,
                category_id,
            ),
            await self._enum_facet(
                "processing",
                "Processing",
                "enum",
                ProductCoffee,
                ProductCoffee.processing,
                category_id,
            ),
            FacetDTO(key="body", label="Body", kind="range", min=1, max=5),
            FacetDTO(key="sweetness", label="Sweetness", kind="range", min=1, max=5),
            await self._range_facet(
                "altitude", "Altitude", ProductCoffee, ProductCoffee.altitude, category_id
            ),
        ]

    async def _equipment_facets(self, category_id: uuid.UUID) -> list[FacetDTO]:
        return [
            await self._enum_facet(
                "equipment_type",
                "Equipment type",
                "multi",
                ProductEquipment,
                ProductEquipment.equipment_type,
                category_id,
            ),
            await self._enum_facet(
                "material",
                "Material",
                "multi",
                ProductEquipment,
                ProductEquipment.material,
                category_id,
            ),
            await self._range_facet(
                "power", "Power (W)", ProductEquipment, ProductEquipment.power_watts, category_id
            ),
            await self._range_facet(
                "warranty",
                "Warranty (months)",
                ProductEquipment,
                ProductEquipment.warranty_months,
                category_id,
            ),
        ]

    async def _accessory_facets(self, category_id: uuid.UUID) -> list[FacetDTO]:
        return [
            await self._enum_facet(
                "accessory_type",
                "Accessory type",
                "multi",
                ProductAccessories,
                ProductAccessories.accessory_type,
                category_id,
            ),
            await self._enum_facet(
                "material",
                "Material",
                "multi",
                ProductAccessories,
                ProductAccessories.material,
                category_id,
            ),
        ]

    async def _consumable_facets(self, category_id: uuid.UUID) -> list[FacetDTO]:
        return [
            await self._enum_facet(
                "consumable_type",
                "Consumable type",
                "multi",
                ProductConsumables,
                ProductConsumables.consumable_type,
                category_id,
            ),
            await self._enum_facet(
                "material",
                "Material",
                "multi",
                ProductConsumables,
                ProductConsumables.material,
                category_id,
            ),
            await self._range_facet(
                "pack",
                "Pack size",
                ProductConsumables,
                ProductConsumables.quantity_per_pack,
                category_id,
            ),
        ]

    async def _flavor_facet(self, category_id: uuid.UUID) -> FacetDTO:
        rows = await self._repo.coffee_flavor_notes(category_id)
        counts: dict[str, int] = {}
        labels: dict[str, str] = {}
        for notes in rows:
            keys = notes.get("keys") or []
            labels_en = notes.get("en") or []
            for i, key in enumerate(keys):
                counts[key] = counts.get(key, 0) + 1
                if key not in labels:
                    labels[key] = labels_en[i] if i < len(labels_en) else _label(key)
        ordered = sorted(counts, key=lambda k: (-counts[k], k))
        options = [FacetOptionDTO(value=k, label=labels[k], count=counts[k]) for k in ordered]
        return FacetDTO(key="flavor_notes", label="Flavor notes", kind="multi", options=options)

    async def _acidity_facet(self, category_id: uuid.UUID) -> FacetDTO:
        buckets = {"soft": 0, "balanced": 0, "bright": 0}
        for value, count in await self._repo.acidity_counts(category_id):
            if value <= 2:
                buckets["soft"] += count
            elif value == 3:
                buckets["balanced"] += count
            else:
                buckets["bright"] += count
        options = [
            FacetOptionDTO(value=key, label=_ACIDITY_LABELS[key], count=buckets[key])
            for key in ("soft", "balanced", "bright")
        ]
        return FacetDTO(key="acidity", label="Acidity", kind="enum", options=options)
