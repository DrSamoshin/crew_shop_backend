"""Auth enums."""

import enum


class Provider(enum.StrEnum):
    """Supported OAuth identity providers."""

    APPLE = "apple"
    GOOGLE = "google"
