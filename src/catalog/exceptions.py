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


class CategoryNotFoundError(CatalogException):
    """No category exists for the requested id."""

    def __init__(self, category_id: str) -> None:
        super().__init__(
            f"Category {category_id} not found",
            status_code=404,
            error_code="CATEGORY_NOT_FOUND",
        )


class CatalogReferenceError(CatalogException):
    """A write references a non-existent category or product type."""

    def __init__(self, reference: str, value: str) -> None:
        super().__init__(
            f"Unknown {reference}: {value}",
            status_code=400,
            error_code="CATALOG_INVALID_REFERENCE",
        )


class ProductTypeMismatchError(CatalogException):
    """The supplied attribute block does not match the product's type."""

    def __init__(self, expected: str) -> None:
        super().__init__(
            f"Expected attributes for product type '{expected}'",
            status_code=400,
            error_code="CATALOG_PRODUCT_TYPE_MISMATCH",
        )


class CategoryNotEmptyError(CatalogException):
    """A category still has products and cannot be deleted."""

    def __init__(self, category_id: str) -> None:
        super().__init__(
            f"Category {category_id} still has products",
            status_code=409,
            error_code="CATALOG_CATEGORY_NOT_EMPTY",
        )


class AdminForbiddenError(CatalogException):
    """The admin S2S service credential is missing or invalid."""

    def __init__(self, message: str = "Invalid admin service credential") -> None:
        super().__init__(message, status_code=403, error_code="CATALOG_ADMIN_FORBIDDEN")
