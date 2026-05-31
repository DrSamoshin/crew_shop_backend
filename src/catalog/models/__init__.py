"""Catalog ORM models. Importing this package registers every mapper on ``Base.metadata``."""

from src.catalog.models.accessory import ProductAccessories
from src.catalog.models.coffee import ProductCoffee
from src.catalog.models.compatibility import ProductCompatibility
from src.catalog.models.consumable import ProductConsumables
from src.catalog.models.equipment import ProductEquipment
from src.catalog.models.product import Product
from src.catalog.models.product_category import ProductCategory
from src.catalog.models.product_type import ProductType

__all__ = [
    "ProductCategory",
    "Product",
    "ProductAccessories",
    "ProductCoffee",
    "ProductCompatibility",
    "ProductConsumables",
    "ProductEquipment",
    "ProductType",
]
