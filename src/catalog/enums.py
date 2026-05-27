"""Catalog enums. Values are the exact strings persisted and enforced by CHECK constraints."""

import enum


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


def _quote_csv(values: type[enum.StrEnum]) -> str:
    """Render an enum's values as a SQL string list, e.g. ``'a', 'b'`` for IN checks."""
    return ", ".join(f"'{member.value}'" for member in values)
