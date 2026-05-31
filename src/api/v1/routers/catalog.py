"""Public catalog endpoints: product list with two-tier filtering, detail, search, categories.

All endpoints are public (no auth). Coffee filters apply only when set; with no coffee filter
the listing spans every product type. The rating aggregate is read-only (Ratings feature owns
writes). Errors flow through the shared AppException envelope.
"""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.database import get_db
from src.auth.dependencies import optional_auth
from src.catalog.schemas.catalog import (
    AcidityBucket,
    CategoryFacetsDTO,
    ProductCategoryListDTO,
    ProductDetailDTO,
    ProductListDTO,
    SortOption,
    build_product_filters,
)
from src.catalog.services.facets_service import FacetsService
from src.catalog.services.product_category_service import ProductCategoryService
from src.catalog.services.product_service import ProductService
from src.users.models import User

router = APIRouter(prefix="/catalog", tags=["catalog"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
UserOptDep = Annotated[User | None, Depends(optional_auth)]


@router.get(
    "/products",
    response_model=ProductListDTO,
    summary="List products with two-tier filters, sorting and pagination",
)
async def list_products(
    db: DbDep,
    user: UserOptDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: SortOption = SortOption.NEWEST,
    # Scope to one category; the backend resolves its product_type to validate per-type facets.
    product_category_id: uuid.UUID | None = None,
    # Universal facets (valid with or without a category).
    price_min: Annotated[Decimal | None, Query(gt=0)] = None,
    price_max: Annotated[Decimal | None, Query(gt=0)] = None,
    min_rating: Annotated[float | None, Query(ge=0, le=5)] = None,
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
    # Per-type facets (valid only when product_category_id resolves to the matching type).
    equipment_type: str | None = None,
    power_min: Annotated[int | None, Query(ge=0)] = None,
    power_max: Annotated[int | None, Query(ge=0)] = None,
    warranty_min: Annotated[int | None, Query(ge=0)] = None,
    accessory_type: str | None = None,
    consumable_type: str | None = None,
    pack_min: Annotated[int | None, Query(ge=1)] = None,
    pack_max: Annotated[int | None, Query(ge=1)] = None,
    material: str | None = None,
) -> ProductListDTO:
    filters = build_product_filters(
        product_category_id=product_category_id,
        price_min=price_min,
        price_max=price_max,
        min_rating=min_rating,
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
        equipment_type=equipment_type,
        power_min=power_min,
        power_max=power_max,
        warranty_min=warranty_min,
        accessory_type=accessory_type,
        consumable_type=consumable_type,
        pack_min=pack_min,
        pack_max=pack_max,
        material=material,
    )
    user_id = user.id if user else None
    return await ProductService(db).list_products(filters, sort, limit, offset, user_id=user_id)


@router.get("/search", response_model=ProductListDTO, summary="Search products by name")
async def search_products(
    db: DbDep,
    user: UserOptDep,
    q: Annotated[str, Query(min_length=2, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductListDTO:
    return await ProductService(db).search_products(
        q, limit, offset, user_id=user.id if user else None
    )


@router.get(
    "/product-categories", response_model=ProductCategoryListDTO, summary="List active categories"
)
async def list_categories(db: DbDep) -> ProductCategoryListDTO:
    return await ProductCategoryService(db).list_categories()


@router.get(
    "/product-categories/{product_category_id}/facets",
    response_model=CategoryFacetsDTO,
    summary="Filter schema and dynamic option lists for a category",
)
async def category_facets(product_category_id: uuid.UUID, db: DbDep) -> CategoryFacetsDTO:
    return await FacetsService(db).get_facets(product_category_id)


@router.get(
    "/products/{product_id}",
    response_model=ProductDetailDTO,
    summary="Get product detail",
)
async def get_product(product_id: uuid.UUID, db: DbDep, user: UserOptDep) -> ProductDetailDTO:
    return await ProductService(db).get_product(product_id, user_id=user.id if user else None)
