import enum
from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(UTC)


def sql_str_list(values: type[enum.StrEnum]) -> str:
    """Render an enum's values as a SQL string list, e.g. ``'a', 'b'`` for IN/CHECK clauses."""
    return ", ".join(f"'{member.value}'" for member in values)
