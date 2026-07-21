"""Admin (S2S-gated) catalog write endpoints, separate from the public read API.

Trusted only for the crew_admin backend: every request carries the per-environment service
token, and the acting operator/role is recorded for audit. Validation is authoritative; errors
flow through the shared AppException envelope.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.catalog.admin.dependencies import ServiceCaller, audit, require_service_caller
from src.catalog.admin.schemas import (
    ProductCategoryCreate,
    ProductCategoryUpdate,
    ProductCreate,
    ProductUpdate,
)
from src.catalog.admin.service import AdminCatalogService
from src.catalog.schemas.catalog import (
    ProductCategoryDTO,
    ProductCategoryListDTO,
    ProductDetailDTO,
)

router = APIRouter(prefix="/admin/catalog", tags=["catalog-admin"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
CallerDep = Annotated[ServiceCaller, Depends(require_service_caller)]


@router.post(
    "/products",
    response_model=ProductDetailDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create a product",
)
async def create_product(payload: ProductCreate, db: DbDep, caller: CallerDep) -> ProductDetailDTO:
    product = await AdminCatalogService(db).create_product(payload)
    audit(caller, "create", f"product:{product.id}")
    return product


@router.put("/products/{product_id}", response_model=ProductDetailDTO, summary="Replace a product")
async def update_product(
    product_id: uuid.UUID, payload: ProductUpdate, db: DbDep, caller: CallerDep
) -> ProductDetailDTO:
    product = await AdminCatalogService(db).update_product(product_id, payload)
    audit(caller, "update", f"product:{product_id}")
    return product


@router.delete(
    "/products/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a product",
)
async def delete_product(product_id: uuid.UUID, db: DbDep, caller: CallerDep) -> None:
    await AdminCatalogService(db).delete_product(product_id)
    audit(caller, "delete", f"product:{product_id}")


@router.get(
    "/product-categories",
    response_model=ProductCategoryListDTO,
    summary="List all categories (active and inactive)",
)
async def list_categories(db: DbDep, caller: CallerDep) -> ProductCategoryListDTO:
    return await AdminCatalogService(db).list_categories()


@router.post(
    "/product-categories",
    response_model=ProductCategoryDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Create a category",
)
async def create_category(
    payload: ProductCategoryCreate, db: DbDep, caller: CallerDep
) -> ProductCategoryDTO:
    category = await AdminCatalogService(db).create_category(payload)
    audit(caller, "create", f"category:{category.id}")
    return category


@router.put(
    "/product-categories/{product_category_id}",
    response_model=ProductCategoryDTO,
    summary="Update a category",
)
async def update_category(
    product_category_id: uuid.UUID, payload: ProductCategoryUpdate, db: DbDep, caller: CallerDep
) -> ProductCategoryDTO:
    category = await AdminCatalogService(db).update_category(product_category_id, payload)
    audit(caller, "update", f"category:{product_category_id}")
    return category


@router.delete(
    "/product-categories/{product_category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a category",
)
async def delete_category(product_category_id: uuid.UUID, db: DbDep, caller: CallerDep) -> None:
    await AdminCatalogService(db).delete_category(product_category_id)
    audit(caller, "delete", f"category:{product_category_id}")
