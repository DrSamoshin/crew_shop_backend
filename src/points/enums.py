"""Point enums. Values are the exact strings persisted and enforced by CHECK constraints."""

import enum


class PointType(enum.StrEnum):
    """Business location types. Only ``coffeeshop`` points serve order pickup."""

    COFFEESHOP = "coffeeshop"
    WAREHOUSE = "warehouse"
    ROASTERY = "roastery"
