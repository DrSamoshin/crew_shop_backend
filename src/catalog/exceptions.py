"""Catalog error types, served through the standard AppException handlers."""

from src.api.exceptions import AppException


class CatalogException(AppException):
    """Base for catalog domain errors."""


class ProductNotFoundError(CatalogException):
    """No product exists for the requested id."""

    def __init__(self, product_id: str) -> None:
        super().__init__(
            f"Product {product_id} not found",
            status_code=404,
            error_code="PRODUCT_NOT_FOUND",
        )


class CatalogInvalidFilterError(CatalogException):
    """A filter value is malformed or outside the allowed set."""

    def __init__(self, filter_name: str, value: str) -> None:
        super().__init__(
            f"Invalid {filter_name}: {value}",
            status_code=400,
            error_code="CATALOG_INVALID_FILTER",
        )
