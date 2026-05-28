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

from src.catalog.enums import ProcessingMethod, RoastLevel
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
    category_id: uuid.UUID
    name: str
    description: str | None
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


class CategoryDTO(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None


class CategoryListDTO(BaseModel):
    items: list[CategoryDTO]
    total: int


# ------------------------------------------------------------------- request filters


@dataclass(frozen=True, slots=True)
class ProductFilters:
    """Normalized two-tier coffee filters. Coffee filters are applied only when set."""

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


def _split_csv(raw: str | None) -> tuple[str, ...]:
    """Split a comma-separated filter value into normalized (lowercased, deduped) terms."""
    if not raw:
        return ()
    return tuple({part.strip().lower(): None for part in raw.split(",") if part.strip()})


def _validate_range(name: str, low: int | None, high: int | None) -> None:
    if low is not None and high is not None and low > high:
        raise CatalogInvalidFilterError(name, f"{low} > {high}")


def build_product_filters(
    *,
    flavor_notes: str | None,
    acidity: AcidityBucket | None,
    region: str | None,
    roast_level: str | None,
    processing: str | None,
    body_min: int | None,
    body_max: int | None,
    sweetness_min: int | None,
    sweetness_max: int | None,
    altitude_min: int | None,
    altitude_max: int | None,
) -> ProductFilters:
    """Parse and validate the raw query parameters into a ``ProductFilters``."""
    roasts = _split_csv(roast_level)
    for value in roasts:
        if value not in set(RoastLevel):
            raise CatalogInvalidFilterError("roast_level", value)
    processings = _split_csv(processing)
    for value in processings:
        if value not in set(ProcessingMethod):
            raise CatalogInvalidFilterError("processing", value)

    _validate_range("body", body_min, body_max)
    _validate_range("sweetness", sweetness_min, sweetness_max)
    _validate_range("altitude", altitude_min, altitude_max)

    return ProductFilters(
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
    )
