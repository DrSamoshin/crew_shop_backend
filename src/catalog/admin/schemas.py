"""Admin write request DTOs. Server-side validation is authoritative."""

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.catalog.enums import (
    AccessoryType,
    ConsumableType,
    EquipmentType,
    ProcessingMethod,
    ProductTypeName,
    RoastLevel,
)

# product_type -> the request field carrying its attributes.
ATTR_FIELD: dict[ProductTypeName, str] = {
    ProductTypeName.COFFEE: "coffee",
    ProductTypeName.EQUIPMENT: "equipment",
    ProductTypeName.ACCESSORIES: "accessory",
    ProductTypeName.CONSUMABLES: "consumable",
}


class CoffeeAttributesIn(BaseModel):
    region: str = Field(min_length=1, max_length=100)
    roast_level: RoastLevel
    processing: ProcessingMethod
    acidity: int = Field(ge=1, le=5)
    body: int = Field(ge=1, le=5)
    sweetness: int = Field(ge=1, le=5)
    altitude: int | None = Field(default=None, ge=0)
    flavor_notes: dict[str, list[str]] | None = None


class EquipmentAttributesIn(BaseModel):
    equipment_type: EquipmentType
    power_watts: int | None = Field(default=None, gt=0)
    warranty_months: int | None = Field(default=None, ge=0)
    width_cm: Decimal | None = Field(default=None, gt=0)
    height_cm: Decimal | None = Field(default=None, gt=0)
    depth_cm: Decimal | None = Field(default=None, gt=0)
    weight_kg: Decimal | None = Field(default=None, gt=0)
    material: str | None = Field(default=None, max_length=100)
    other_options: dict[str, Any] | None = None


class AccessoryAttributesIn(BaseModel):
    accessory_type: AccessoryType
    material: str = Field(min_length=1, max_length=100)
    other_options: dict[str, Any] | None = None


class ConsumableAttributesIn(BaseModel):
    consumable_type: ConsumableType
    quantity_per_pack: int = Field(ge=1)
    unit_description: str = Field(min_length=1, max_length=50)
    material: str | None = Field(default=None, max_length=100)
    expiry_months: int | None = Field(default=None, ge=1)
    storage_conditions: str | None = Field(default=None, max_length=255)
    other_options: dict[str, Any] | None = None


ProductAttributesIn = (
    CoffeeAttributesIn | EquipmentAttributesIn | AccessoryAttributesIn | ConsumableAttributesIn
)


class _ProductWrite(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    image_url: str | None = Field(default=None, max_length=500)
    product_category_id: uuid.UUID
    price: Decimal = Field(gt=0)
    currency: str = Field(default="EUR", min_length=3, max_length=3)
    coffee: CoffeeAttributesIn | None = None
    equipment: EquipmentAttributesIn | None = None
    accessory: AccessoryAttributesIn | None = None
    consumable: ConsumableAttributesIn | None = None

    def attributes(self) -> ProductAttributesIn:
        """The single provided attribute block (callers ensure exactly one is set)."""
        block = self.coffee or self.equipment or self.accessory or self.consumable
        assert block is not None  # guaranteed by validators
        return block


class ProductCreate(_ProductWrite):
    product_type: ProductTypeName

    @model_validator(mode="after")
    def _attributes_match_type(self) -> "ProductCreate":
        blocks = {
            ProductTypeName.COFFEE: self.coffee,
            ProductTypeName.EQUIPMENT: self.equipment,
            ProductTypeName.ACCESSORIES: self.accessory,
            ProductTypeName.CONSUMABLES: self.consumable,
        }
        if blocks[self.product_type] is None:
            raise ValueError(f"missing '{ATTR_FIELD[self.product_type]}' attributes")
        extra = [ATTR_FIELD[t] for t, b in blocks.items() if t != self.product_type and b]
        if extra:
            raise ValueError(
                f"unexpected attribute blocks for product_type {self.product_type.value}"
            )
        return self


class ProductUpdate(_ProductWrite):
    @model_validator(mode="after")
    def _exactly_one_block(self) -> "ProductUpdate":
        present = [b for b in (self.coffee, self.equipment, self.accessory, self.consumable) if b]
        if len(present) != 1:
            raise ValueError("exactly one attribute block is required")
        return self


class ProductCategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    # Each category belongs to exactly one product type (drives its facet set).
    product_type: ProductTypeName
    is_active: bool = True


class ProductCategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    product_type: ProductTypeName | None = None
    is_active: bool | None = None
