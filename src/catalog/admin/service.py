"""Admin write operations for products and categories. Server-side validation is authoritative."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.catalog.admin.schemas import (
    AccessoryAttributesIn,
    CoffeeAttributesIn,
    EquipmentAttributesIn,
    ProductAttributesIn,
    ProductCategoryCreate,
    ProductCategoryUpdate,
    ProductCreate,
    ProductUpdate,
)
from src.catalog.enums import ProductTypeName
from src.catalog.exceptions import (
    CatalogReferenceError,
    ProductCategoryNotEmptyError,
    ProductCategoryNotFoundError,
    ProductNotFoundError,
    ProductTypeMismatchError,
)
from src.catalog.models import (
    Product,
    ProductAccessories,
    ProductCategory,
    ProductCoffee,
    ProductConsumables,
    ProductEquipment,
    ProductType,
)
from src.catalog.schemas.catalog import ProductCategoryDTO, ProductDetailDTO
from src.catalog.services.product_service import ProductService

_SubtypeModel = ProductCoffee | ProductEquipment | ProductAccessories | ProductConsumables

_SUBTYPE_MODEL: dict[ProductTypeName, type[_SubtypeModel]] = {
    ProductTypeName.COFFEE: ProductCoffee,
    ProductTypeName.EQUIPMENT: ProductEquipment,
    ProductTypeName.ACCESSORIES: ProductAccessories,
    ProductTypeName.CONSUMABLES: ProductConsumables,
}


def _block_type(block: ProductAttributesIn) -> ProductTypeName:
    if isinstance(block, CoffeeAttributesIn):
        return ProductTypeName.COFFEE
    if isinstance(block, EquipmentAttributesIn):
        return ProductTypeName.EQUIPMENT
    if isinstance(block, AccessoryAttributesIn):
        return ProductTypeName.ACCESSORIES
    return ProductTypeName.CONSUMABLES


def _subtype_row(
    product_id: uuid.UUID, product_type: ProductTypeName, attrs: ProductAttributesIn
) -> _SubtypeModel:
    if isinstance(attrs, CoffeeAttributesIn):
        return ProductCoffee(
            id=product_id,
            region=attrs.region,
            roast_level=attrs.roast_level,
            processing=attrs.processing,
            acidity=attrs.acidity,
            body=attrs.body,
            sweetness=attrs.sweetness,
            altitude=attrs.altitude,
            flavor_notes=attrs.flavor_notes,
        )
    if isinstance(attrs, EquipmentAttributesIn):
        return ProductEquipment(
            id=product_id,
            equipment_type=attrs.equipment_type,
            power_watts=attrs.power_watts,
            warranty_months=attrs.warranty_months,
            width_cm=attrs.width_cm,
            height_cm=attrs.height_cm,
            depth_cm=attrs.depth_cm,
            weight_kg=attrs.weight_kg,
            material=attrs.material,
            other_options=attrs.other_options,
        )
    if isinstance(attrs, AccessoryAttributesIn):
        return ProductAccessories(
            id=product_id,
            accessory_type=attrs.accessory_type,
            material=attrs.material,
            other_options=attrs.other_options,
        )
    return ProductConsumables(
        id=product_id,
        consumable_type=attrs.consumable_type,
        quantity_per_pack=attrs.quantity_per_pack,
        unit_description=attrs.unit_description,
        material=attrs.material,
        expiry_months=attrs.expiry_months,
        storage_conditions=attrs.storage_conditions,
        other_options=attrs.other_options,
    )


class AdminCatalogService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _resolve_product_type(self, name: ProductTypeName) -> uuid.UUID:
        type_id = await self._db.scalar(
            select(ProductType.id).where(ProductType.name == name.value)
        )
        if type_id is None:
            raise CatalogReferenceError("product_type", name.value)
        return type_id

    async def _require_category(self, product_category_id: uuid.UUID) -> None:
        exists = await self._db.scalar(
            select(ProductCategory.id).where(ProductCategory.id == product_category_id)
        )
        if exists is None:
            raise CatalogReferenceError("product_category_id", str(product_category_id))

    async def create_product(self, data: ProductCreate) -> ProductDetailDTO:
        await self._require_category(data.product_category_id)
        type_id = await self._resolve_product_type(data.product_type)
        product = Product(
            name=data.name,
            description=data.description,
            image_url=data.image_url,
            product_category_id=data.product_category_id,
            product_type_id=type_id,
            price=data.price,
            currency=data.currency,
        )
        self._db.add(product)
        await self._db.flush()
        self._db.add(_subtype_row(product.id, data.product_type, data.attributes()))
        await self._db.flush()
        return await ProductService(self._db).get_product(product.id)

    async def update_product(self, product_id: uuid.UUID, data: ProductUpdate) -> ProductDetailDTO:
        product = await self._db.get(Product, product_id)
        if product is None:
            raise ProductNotFoundError(str(product_id))
        await self._require_category(data.product_category_id)

        type_name = await self._db.scalar(
            select(ProductType.name).where(ProductType.id == product.product_type_id)
        )
        if type_name is None:
            raise ProductNotFoundError(str(product_id))
        product_type = ProductTypeName(type_name)
        attrs = data.attributes()
        if _block_type(attrs) is not product_type:
            raise ProductTypeMismatchError(product_type.value)

        product.name = data.name
        product.description = data.description
        product.image_url = data.image_url
        product.product_category_id = data.product_category_id
        product.price = data.price
        product.currency = data.currency

        existing_subtype = await self._db.get(_SUBTYPE_MODEL[product_type], product_id)
        if existing_subtype is not None:
            await self._db.delete(existing_subtype)
            await self._db.flush()
        self._db.add(_subtype_row(product_id, product_type, attrs))
        await self._db.flush()
        return await ProductService(self._db).get_product(product_id)

    async def delete_product(self, product_id: uuid.UUID) -> None:
        product = await self._db.get(Product, product_id)
        if product is None:
            raise ProductNotFoundError(str(product_id))
        await self._db.delete(product)
        await self._db.flush()

    async def _product_type_name(self, type_id: uuid.UUID) -> str:
        name = await self._db.scalar(select(ProductType.name).where(ProductType.id == type_id))
        if name is None:  # pragma: no cover - FK guarantees existence
            raise CatalogReferenceError("product_type_id", str(type_id))
        return name

    async def create_category(self, data: ProductCategoryCreate) -> ProductCategoryDTO:
        type_id = await self._resolve_product_type(data.product_type)
        category = ProductCategory(
            name=data.name,
            description=data.description,
            product_type_id=type_id,
            is_active=data.is_active,
        )
        self._db.add(category)
        await self._db.flush()
        return ProductCategoryDTO(
            id=category.id,
            name=category.name,
            description=category.description,
            product_type=data.product_type.value,
        )

    async def update_category(
        self, product_category_id: uuid.UUID, data: ProductCategoryUpdate
    ) -> ProductCategoryDTO:
        category = await self._db.get(ProductCategory, product_category_id)
        if category is None:
            raise ProductCategoryNotFoundError(str(product_category_id))
        if data.name is not None:
            category.name = data.name
        if data.is_active is not None:
            category.is_active = data.is_active
        if data.product_type is not None:
            category.product_type_id = await self._resolve_product_type(data.product_type)
        category.description = data.description
        await self._db.flush()
        return ProductCategoryDTO(
            id=category.id,
            name=category.name,
            description=category.description,
            product_type=await self._product_type_name(category.product_type_id),
        )

    async def delete_category(self, product_category_id: uuid.UUID) -> None:
        category = await self._db.get(ProductCategory, product_category_id)
        if category is None:
            raise ProductCategoryNotFoundError(str(product_category_id))
        product_count = await self._db.scalar(
            select(func.count())
            .select_from(Product)
            .where(Product.product_category_id == product_category_id)
        )
        if product_count:
            raise ProductCategoryNotEmptyError(str(product_category_id))
        await self._db.delete(category)
        await self._db.flush()
