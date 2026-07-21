"""Catalog request filters and response DTOs.

Filter values are stored lowercase; ``build_product_filters`` normalizes and validates the
raw query strings, raising ``CATALOG_INVALID_FILTER`` for unknown roast/processing values or
inverted ranges. Responses carry per-type attribute objects (only the matching one is set)
plus the read-only rating aggregate.
"""

import enum
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any

from pydantic import BaseModel, PlainSerializer

from src.catalog.enums import (
    AccessoryType,
    ConsumableType,
    EquipmentType,
    ProcessingMethod,
    RoastLevel,
)
from src.catalog.exceptions import CatalogInvalidFilterError

# Decimals serialize to a plain string ("14.50") in JSON to preserve precision.
DecimalStr = Annotated[
    Decimal, PlainSerializer(lambda v: format(v, "f"), return_type=str, when_used="json")
]


class SortOption(enum.StrEnum):
    """Supported product orderings. Rating/popularity sorts await the Ratings feature."""

    NEWEST = "newest"
    PRICE_ASC = "price_asc"
    PRICE_DESC = "price_desc"


class AcidityBucket(enum.StrEnum):
    """Emotional acidity filter mapped to a 1-5 range: soft 1-2, balanced 3, bright 4-5."""

    SOFT = "soft"
    BALANCED = "balanced"
    BRIGHT = "bright"


# --------------------------------------------------------------------- response DTOs


class CoffeeAttributesDTO(BaseModel):
    region: str
    roast_level: str
    processing: str
    acidity: int
    body: int
    sweetness: int
    altitude: int | None
    flavor_notes: dict[str, list[str]] | None


class EquipmentAttributesDTO(BaseModel):
    equipment_type: str
    power_watts: int | None
    warranty_months: int | None
    width_cm: DecimalStr | None
    height_cm: DecimalStr | None
    depth_cm: DecimalStr | None
    weight_kg: DecimalStr | None
    material: str | None
    other_options: dict[str, Any] | None


class AccessoryAttributesDTO(BaseModel):
    accessory_type: str
    material: str
    other_options: dict[str, Any] | None


class ConsumableAttributesDTO(BaseModel):
    consumable_type: str
    quantity_per_pack: int
    unit_description: str
    material: str | None
    expiry_months: int | None
    storage_conditions: str | None
    other_options: dict[str, Any] | None


class ProductDTO(BaseModel):
    """A catalog product with its type-specific attributes and rating aggregate."""

    id: uuid.UUID
    product_category_id: uuid.UUID
    name: str
    description: str | None
    image_url: str | None
    price: DecimalStr
    currency: str
    product_type: str
    is_active: bool
    rating: float | None
    rating_count: int
    # Per-user enrichment from the Ratings feature. ``user_rating`` is the caller's current
    # 1-5 score (null when not rated or anonymous); ``can_rate`` reflects purchase verification.
    user_rating: int | None = None
    can_rate: bool = False
    coffee: CoffeeAttributesDTO | None = None
    equipment: EquipmentAttributesDTO | None = None
    accessory: AccessoryAttributesDTO | None = None
    consumable: ConsumableAttributesDTO | None = None


class ProductDetailDTO(ProductDTO):
    category_name: str
    rating_distribution: dict[str, int] | None = None
    created_at: datetime
    updated_at: datetime


class ProductListDTO(BaseModel):
    items: list[ProductDTO]
    total: int
    limit: int
    offset: int


class ProductCategoryDTO(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    # The category's single product type (coffee | equipment | accessories | consumables);
    # drives which facet set the storefront renders for the category.
    product_type: str


class ProductCategoryListDTO(BaseModel):
    items: list[ProductCategoryDTO]
    total: int


class FacetOptionDTO(BaseModel):
    """A selectable value for an enum/multi facet, with a best-effort match count."""

    value: str
    label: str
    count: int


class FacetDTO(BaseModel):
    """One filter field. ``enum``/``multi`` carry ``options``; ``range`` carries ``min``/``max``."""

    key: str
    label: str
    kind: str  # enum | multi | range
    options: list[FacetOptionDTO] = []
    min: int | None = None
    max: int | None = None


class CategoryFacetsDTO(BaseModel):
    """The filter schema for one category: its product type and the facets to render."""

    product_category_id: uuid.UUID
    product_type: str
    facets: list[FacetDTO]


# ------------------------------------------------------------------- request filters


@dataclass(frozen=True, slots=True)
class ProductFilters:
    """Normalized catalog filters.

    Coffee facets are legacy and apply whenever set. The per-type facets (equipment /
    accessory / consumable) apply only when the scoped category resolves to the matching
    ``product_type`` — that check lives in the service, which resolves the category. Universal
    facets (scope, price, rating) apply regardless.
    """

    # Scope + universal.
    product_category_id: uuid.UUID | None = None
    price_min: Decimal | None = None
    price_max: Decimal | None = None
    min_rating: float | None = None

    # Coffee facets.
    flavor_notes: tuple[str, ...] = ()
    acidity: AcidityBucket | None = None
    region: tuple[str, ...] = ()
    roast_level: tuple[str, ...] = ()
    processing: tuple[str, ...] = ()
    body_min: int | None = None
    body_max: int | None = None
    sweetness_min: int | None = None
    sweetness_max: int | None = None
    altitude_min: int | None = None
    altitude_max: int | None = None

    # Equipment facets.
    equipment_type: tuple[str, ...] = ()
    power_min: int | None = None
    power_max: int | None = None
    warranty_min: int | None = None

    # Accessory facets.
    accessory_type: tuple[str, ...] = ()

    # Consumable facets.
    consumable_type: tuple[str, ...] = ()
    pack_min: int | None = None
    pack_max: int | None = None

    # Material is shared by equipment / accessory / consumable.
    material: tuple[str, ...] = ()

    @property
    def has_coffee_filter(self) -> bool:
        return (
            bool(self.flavor_notes or self.region or self.roast_level or self.processing)
            or self.acidity is not None
            or any(
                value is not None
                for value in (
                    self.body_min,
                    self.body_max,
                    self.sweetness_min,
                    self.sweetness_max,
                    self.altitude_min,
                    self.altitude_max,
                )
            )
        )

    @property
    def has_equipment_filter(self) -> bool:
        return bool(self.equipment_type) or any(
            v is not None for v in (self.power_min, self.power_max, self.warranty_min)
        )

    @property
    def has_accessory_filter(self) -> bool:
        return bool(self.accessory_type)

    @property
    def has_consumable_filter(self) -> bool:
        return bool(self.consumable_type) or any(
            v is not None for v in (self.pack_min, self.pack_max)
        )

    @property
    def has_material_filter(self) -> bool:
        return bool(self.material)


def _split_csv(raw: str | None) -> tuple[str, ...]:
    """Split a comma-separated filter value into normalized (lowercased, deduped) terms."""
    if not raw:
        return ()
    return tuple({part.strip().lower(): None for part in raw.split(",") if part.strip()})


def _validate_range(name: str, low: float | Decimal | None, high: float | Decimal | None) -> None:
    if low is not None and high is not None and low > high:
        raise CatalogInvalidFilterError(name, f"{low} > {high}")


def _validate_enum_csv(name: str, values: tuple[str, ...], allowed: type[enum.StrEnum]) -> None:
    members = set(allowed)
    for value in values:
        if value not in members:
            raise CatalogInvalidFilterError(name, value)


def build_product_filters(
    *,
    product_category_id: uuid.UUID | None = None,
    price_min: Decimal | None = None,
    price_max: Decimal | None = None,
    min_rating: float | None = None,
    flavor_notes: str | None = None,
    acidity: AcidityBucket | None = None,
    region: str | None = None,
    roast_level: str | None = None,
    processing: str | None = None,
    body_min: int | None = None,
    body_max: int | None = None,
    sweetness_min: int | None = None,
    sweetness_max: int | None = None,
    altitude_min: int | None = None,
    altitude_max: int | None = None,
    equipment_type: str | None = None,
    power_min: int | None = None,
    power_max: int | None = None,
    warranty_min: int | None = None,
    accessory_type: str | None = None,
    consumable_type: str | None = None,
    pack_min: int | None = None,
    pack_max: int | None = None,
    material: str | None = None,
) -> ProductFilters:
    """Parse and validate the raw query parameters into a ``ProductFilters``.

    Validates enum membership and range ordering here; whether a per-type facet is allowed for
    the scoped category is checked later in the service (it needs to resolve the category).
    """
    roasts = _split_csv(roast_level)
    _validate_enum_csv("roast_level", roasts, RoastLevel)
    processings = _split_csv(processing)
    _validate_enum_csv("processing", processings, ProcessingMethod)
    equipment_types = _split_csv(equipment_type)
    _validate_enum_csv("equipment_type", equipment_types, EquipmentType)
    accessory_types = _split_csv(accessory_type)
    _validate_enum_csv("accessory_type", accessory_types, AccessoryType)
    consumable_types = _split_csv(consumable_type)
    _validate_enum_csv("consumable_type", consumable_types, ConsumableType)

    _validate_range("body", body_min, body_max)
    _validate_range("sweetness", sweetness_min, sweetness_max)
    _validate_range("altitude", altitude_min, altitude_max)
    _validate_range("price", price_min, price_max)
    _validate_range("power", power_min, power_max)
    _validate_range("pack", pack_min, pack_max)

    return ProductFilters(
        product_category_id=product_category_id,
        price_min=price_min,
        price_max=price_max,
        min_rating=min_rating,
        flavor_notes=_split_csv(flavor_notes),
        acidity=acidity,
        region=_split_csv(region),
        roast_level=roasts,
        processing=processings,
        body_min=body_min,
        body_max=body_max,
        sweetness_min=sweetness_min,
        sweetness_max=sweetness_max,
        altitude_min=altitude_min,
        altitude_max=altitude_max,
        equipment_type=equipment_types,
        power_min=power_min,
        power_max=power_max,
        warranty_min=warranty_min,
        accessory_type=accessory_types,
        consumable_type=consumable_types,
        pack_min=pack_min,
        pack_max=pack_max,
        material=_split_csv(material),
    )
