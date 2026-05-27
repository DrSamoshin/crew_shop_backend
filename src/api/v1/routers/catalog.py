"""Public catalog endpoints: product list with two-tier filtering, detail, search, categories.

All endpoints are public (no auth). Coffee filters apply only when set; with no coffee filter
the listing spans every product type. The rating aggregate is read-only (Ratings feature owns
writes). Errors flow through the shared AppException envelope.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.catalog.schemas.catalog import (
    AcidityBucket,
    CategoryListDTO,
    ProductDetailDTO,
    ProductListDTO,
    SortOption,
    build_product_filters,
)
from src.catalog.services.category_service import CategoryService
from src.catalog.services.product_service import ProductService

router = APIRouter(prefix="/catalog", tags=["catalog"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get(
    "/products",
    response_model=ProductListDTO,
    summary="List products with two-tier filters, sorting and pagination",
)
async def list_products(
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: SortOption = SortOption.NEWEST,
    # Comma-separated, OR within each facet: flavor keys / regions / roast levels / processing.
    flavor_notes: str | None = None,
    acidity: AcidityBucket | None = None,
    region: str | None = None,
    roast_level: str | None = None,
    processing: str | None = None,
    body_min: Annotated[int | None, Query(ge=1, le=5)] = None,
    body_max: Annotated[int | None, Query(ge=1, le=5)] = None,
    sweetness_min: Annotated[int | None, Query(ge=1, le=5)] = None,
    sweetness_max: Annotated[int | None, Query(ge=1, le=5)] = None,
    altitude_min: Annotated[int | None, Query(ge=0)] = None,
    altitude_max: Annotated[int | None, Query(ge=0)] = None,
) -> ProductListDTO:
    filters = build_product_filters(
        flavor_notes=flavor_notes,
        acidity=acidity,
        region=region,
        roast_level=roast_level,
        processing=processing,
        body_min=body_min,
        body_max=body_max,
        sweetness_min=sweetness_min,
        sweetness_max=sweetness_max,
        altitude_min=altitude_min,
        altitude_max=altitude_max,
    )
    return await ProductService(db).list_products(filters, sort, limit, offset)


@router.get("/search", response_model=ProductListDTO, summary="Search products by name")
async def search_products(
    db: DbDep,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductListDTO:
    return await ProductService(db).search_products(q, limit, offset)


@router.get("/categories", response_model=CategoryListDTO, summary="List active categories")
async def list_categories(db: DbDep) -> CategoryListDTO:
    return await CategoryService(db).list_categories()


@router.get(
    "/products/{product_id}",
    response_model=ProductDetailDTO,
    summary="Get product detail",
)
async def get_product(product_id: uuid.UUID, db: DbDep) -> ProductDetailDTO:
    return await ProductService(db).get_product(product_id)
