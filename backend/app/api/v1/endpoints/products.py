"""
SmartCart 2.0 – Product Catalogue API Endpoints.
Provides:
- Paginated and filtered catalogue product listing (GET /api/v1/products).
- Authoritative product lookup by unique SKU (GET /api/v1/products/sku/{sku}).
- Authoritative product details lookup by UUID (GET /api/v1/products/{product_id}).

Notes on Catalogue Mutations and Search:
1. Product Creation, Updates, and Deactivation:
   Omitted per architecture constraints. ProductService is strictly read-only for
   catalogue browsing, authoritative price resolution, and SKU lookups. It does not
   implement create_product, update_product, or deactivate_product methods, and route
   handlers are forbidden from placing raw SQL or direct repository mutations.
2. Full-Text Search and Autocomplete:
   Omitted pending Phase 6 OpenSearch integration. Endpoints strictly use exact category
   and brand filters supported by PostgreSQL and ProductService.
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    get_optional_current_user,
    get_product_service,
)
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.product import ProductFilterParams, ProductResponse
from app.services.product import ProductService

router = APIRouter(prefix="/products", tags=["Products"])


@router.get(
    "",
    response_model=List[ProductResponse],
    status_code=status.HTTP_200_OK,
    summary="List catalogue products",
    description=(
        "Retrieves products with pagination (skip/limit) and filters (category, brand). "
        "Prices are authoritative database values in Indian paise. Inactive products "
        "are strictly excluded for non-administrators."
    ),
)
async def list_products(
    category: Optional[str] = Query(None, description="Filter products by exact category"),
    brand: Optional[str] = Query(None, description="Filter products by exact brand"),
    is_active: Optional[bool] = Query(True, description="Filter by active status (Admin only for inactive)"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(20, ge=1, le=100, description="Pagination limit (max 100)"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    product_service: ProductService = Depends(get_product_service),
) -> List[ProductResponse]:
    """
    List products with category/brand filtering and pagination.
    Inactive products are hidden from public visitors and customers.
    """
    # Validate filter inputs via schema DTO
    ProductFilterParams(category=category, brand=brand, is_active=is_active, skip=skip, limit=limit)

    is_admin = current_user is not None and current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)

    if not is_admin:
        effective_is_active = True
    else:
        effective_is_active = is_active

    products = await product_service.list_products_filtered(
        category=category,
        brand=brand,
        is_active=effective_is_active,
        skip=skip,
        limit=limit,
    )
    return [ProductResponse.model_validate(p) for p in products]


@router.get(
    "/sku/{sku}",
    response_model=ProductResponse,
    status_code=status.HTTP_200_OK,
    summary="Lookup product by SKU",
    description="Retrieves authoritative product details by unique Stock Keeping Unit (SKU).",
)
async def get_product_by_sku(
    sku: str,
    current_user: Optional[User] = Depends(get_optional_current_user),
    product_service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    """
    Retrieve product by SKU.
    Non-admin callers cannot access inactive products.
    """
    is_admin = current_user is not None and current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
    require_active = not is_admin

    product = await product_service.get_product_by_sku(sku=sku, require_active=require_active)
    return ProductResponse.model_validate(product)


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
    status_code=status.HTTP_200_OK,
    summary="Get product details",
    description="Retrieves authoritative product details by primary key UUID.",
)
async def get_product(
    product_id: UUID,
    current_user: Optional[User] = Depends(get_optional_current_user),
    product_service: ProductService = Depends(get_product_service),
) -> ProductResponse:
    """
    Retrieve product by UUID.
    Non-admin callers cannot access inactive products.
    """
    is_admin = current_user is not None and current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN)
    require_active = not is_admin

    product = await product_service.get_product_by_id(product_id=product_id, require_active=require_active)
    return ProductResponse.model_validate(product)
