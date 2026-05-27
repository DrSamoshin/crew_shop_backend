"""Catalog enums. Values are the exact strings persisted and enforced by CHECK constraints."""

import enum

from src.api.core.utils import sql_str_list as _quote_csv

__all__ = [
    "AccessoryType",
    "ConsumableType",
    "EquipmentType",
    "ProcessingMethod",
    "ProductTypeName",
    "RoastLevel",
    "_quote_csv",
]


class ProductTypeName(enum.StrEnum):
    """The four product types; each has its own attribute subtype table."""

    COFFEE = "coffee"
    EQUIPMENT = "equipment"
    ACCESSORIES = "accessories"
    CONSUMABLES = "consumables"


class RoastLevel(enum.StrEnum):
    """Coffee roast levels (light → dark). Stored normalized; capitalize for display."""

    LIGHT = "light"
    MEDIUM = "medium"
    DARK = "dark"


class ProcessingMethod(enum.StrEnum):
    """Coffee processing methods. Stored normalized; capitalize for display."""

    WASHED = "washed"
    NATURAL = "natural"
    ANAEROBIC = "anaerobic"
    HONEY = "honey"


class EquipmentType(enum.StrEnum):
    """Equipment categories (machines, grinders, brewers, ...). Stored normalized."""

    MACHINE = "machine"
    GRINDER = "grinder"
    BREWER = "brewer"
    SCALE = "scale"
    OTHER = "other"


class AccessoryType(enum.StrEnum):
    """Accessory categories (filters, tampers, scales, ...). Stored normalized."""

    FILTER = "filter"
    TAMPER = "tamper"
    SCALE = "scale"
    PITCHER = "pitcher"
    THERMOMETER = "thermometer"
    KNOCKBOX = "knockbox"
    OTHER = "other"


class ConsumableType(enum.StrEnum):
    """Consumable categories (filters, pods, cleaning supplies, ...). Stored normalized."""

    FILTER = "filter"
    PODS = "pods"
    CLEANING = "cleaning"
    WATER = "water"
    OTHER = "other"
