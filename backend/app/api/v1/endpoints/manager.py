"""
Store Manager product catalogue and inventory management endpoints for SmartCart 2.0.
Provides:
- Product creation, metadata updates, safe deactivation.
- Cloudinary image upload and deletion.
- Store inventory balance views, low-stock alerts, and atomic stock adjustments.
- Complete inventory audit history.
Strictly enforces store-manager store isolation and admin multi-store privileges.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_db,
    get_store_manager_service,
    require_staff,
    resolve_manager_store_id,
)
from app.models.user import User
from app.schemas.inventory import InventoryAuditLogResponse, StockResponse
from app.schemas.manager import (
    ManagerProductResponse,
    ProductCreateManagerRequest,
    ProductUpdateManagerRequest,
    StockAdjustmentRequest,
    StockAdjustmentResponse,
)
from app.services.store_manager import StoreManagerService

router = APIRouter(prefix="/manager", tags=["Store Manager"])


# ============================================================================
# 1. Product Management Endpoints
# ============================================================================

@router.post(
    "/products",
    response_model=ManagerProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create catalogue product with store inventory",
    description=(
        "Creates a new product in the global catalogue and initializes physical stock "
        "and low-stock threshold for the manager's assigned store. "
        "Emits transactional outbox event 'product.created'."
    ),
)
async def create_product(
    payload: ProductCreateManagerRequest,
    store_id: UUID = Depends(resolve_manager_store_id),
    current_user: User = Depends(require_staff),
    service: StoreManagerService = Depends(get_store_manager_service),
    session: AsyncSession = Depends(get_db),
) -> ManagerProductResponse:
    product = await service.create_product(payload, store_id=store_id, user=current_user)
    await session.commit()
    return product


@router.get(
    "/products",
    response_model=List[ManagerProductResponse],
    status_code=status.HTTP_200_OK,
    summary="List products with store inventory context",
    description="List catalogue products enriched with current store inventory balance and low-stock indicators.",
)
async def list_products(
    category: Optional[str] = Query(default=None, description="Filter by category"),
    brand: Optional[str] = Query(default=None, description="Filter by brand"),
    is_active: Optional[bool] = Query(default=None, description="Filter by active status"),
    skip: int = Query(default=0, ge=0, description="Pagination offset"),
    limit: int = Query(default=50, ge=1, le=100, description="Pagination limit"),
    store_id: UUID = Depends(resolve_manager_store_id),
    current_user: User = Depends(require_staff),
    service: StoreManagerService = Depends(get_store_manager_service),
) -> List[ManagerProductResponse]:
    return await service.list_products(
        store_id=store_id,
        user=current_user,
        category=category,
        brand=brand,
        is_active=is_active,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/products/{product_id}",
    response_model=ManagerProductResponse,
    status_code=status.HTTP_200_OK,
    summary="Get product detail with store inventory",
    description="Retrieve product details, uploaded image metadata, and store inventory balance.",
)
async def get_product_detail(
    product_id: UUID,
    store_id: UUID = Depends(resolve_manager_store_id),
    current_user: User = Depends(require_staff),
    service: StoreManagerService = Depends(get_store_manager_service),
) -> ManagerProductResponse:
    return await service.get_product_detail(product_id, store_id=store_id, user=current_user)


@router.patch(
    "/products/{product_id}",
    response_model=ManagerProductResponse,
    status_code=status.HTTP_200_OK,
    summary="Update product information",
    description=(
        "Update product name, description, brand, category, or dynamic attributes. "
        "Modifying 'price_paise' is strictly forbidden for STORE_MANAGER and reserved for ADMIN. "
        "Emits transactional outbox event 'product.updated'."
    ),
)
async def update_product(
    product_id: UUID,
    payload: ProductUpdateManagerRequest,
    store_id: UUID = Depends(resolve_manager_store_id),
    current_user: User = Depends(require_staff),
    service: StoreManagerService = Depends(get_store_manager_service),
    session: AsyncSession = Depends(get_db),
) -> ManagerProductResponse:
    product = await service.update_product(
        product_id=product_id,
        request=payload,
        store_id=store_id,
        user=current_user,
    )
    await session.commit()
    return product


@router.delete(
    "/products/{product_id}",
    response_model=ManagerProductResponse,
    status_code=status.HTTP_200_OK,
    summary="Safe product deactivation",
    description=(
        "Safely deactivates a product (soft delete: is_active = False). "
        "Preserves foreign key integrity with historical customer orders and reservations. "
        "Emits transactional outbox event 'product.deactivated'."
    ),
)
async def deactivate_product(
    product_id: UUID,
    store_id: UUID = Depends(resolve_manager_store_id),
    current_user: User = Depends(require_staff),
    service: StoreManagerService = Depends(get_store_manager_service),
    session: AsyncSession = Depends(get_db),
) -> ManagerProductResponse:
    product = await service.deactivate_product(
        product_id=product_id,
        store_id=store_id,
        user=current_user,
    )
    await session.commit()
    return product


# ============================================================================
# 2. Product Image Endpoints
# ============================================================================

@router.post(
    "/products/{product_id}/image",
    response_model=ManagerProductResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload or replace product image via Cloudinary",
    description=(
        "Uploads image to Cloudinary (JPEG, PNG, WEBP; max 5MB) and stores metadata "
        "in product.attributes['image']. Automatically cleans up previous image on Cloudinary."
    ),
)
async def upload_product_image(
    product_id: UUID,
    file: UploadFile = File(...),
    store_id: UUID = Depends(resolve_manager_store_id),
    current_user: User = Depends(require_staff),
    service: StoreManagerService = Depends(get_store_manager_service),
    session: AsyncSession = Depends(get_db),
) -> ManagerProductResponse:
    file_bytes = await file.read()
    product = await service.upload_product_image(
        product_id=product_id,
        file_bytes=file_bytes,
        filename=file.filename or "image.jpg",
        content_type=file.content_type or "image/jpeg",
        store_id=store_id,
        user=current_user,
    )
    await session.commit()
    return product


@router.delete(
    "/products/{product_id}/image",
    response_model=ManagerProductResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete product image",
    description="Deletes image from Cloudinary and clears image metadata from product attributes.",
)
async def delete_product_image(
    product_id: UUID,
    store_id: UUID = Depends(resolve_manager_store_id),
    current_user: User = Depends(require_staff),
    service: StoreManagerService = Depends(get_store_manager_service),
    session: AsyncSession = Depends(get_db),
) -> ManagerProductResponse:
    product = await service.delete_product_image(
        product_id=product_id,
        store_id=store_id,
        user=current_user,
    )
    await session.commit()
    return product


# ============================================================================
# 3. Store Inventory Management Endpoints
# (Note: /inventory/low-stock declared before /inventory/{product_id})
# ============================================================================

@router.get(
    "/inventory",
    response_model=List[StockResponse],
    status_code=status.HTTP_200_OK,
    summary="List store inventory",
    description="Returns inventory records with physical on-hand, reserved, and available stock for store.",
)
async def get_store_inventory(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    store_id: UUID = Depends(resolve_manager_store_id),
    current_user: User = Depends(require_staff),
    service: StoreManagerService = Depends(get_store_manager_service),
) -> List[StockResponse]:
    return await service.get_store_inventory(
        store_id=store_id,
        user=current_user,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/inventory/low-stock",
    response_model=List[StockResponse],
    status_code=status.HTTP_200_OK,
    summary="List low-stock inventory items",
    description="Returns inventory items where available stock (on_hand - reserved) <= low_stock_threshold.",
)
async def get_low_stock_items(
    store_id: UUID = Depends(resolve_manager_store_id),
    current_user: User = Depends(require_staff),
    service: StoreManagerService = Depends(get_store_manager_service),
) -> List[StockResponse]:
    return await service.get_low_stock_items(store_id=store_id, user=current_user)


@router.get(
    "/inventory/{product_id}",
    response_model=StockResponse,
    status_code=status.HTTP_200_OK,
    summary="Get single product store inventory balance",
    description="Inspect on-hand, reserved, and available stock for a specific product at the store.",
)
async def get_product_inventory(
    product_id: UUID,
    store_id: UUID = Depends(resolve_manager_store_id),
    current_user: User = Depends(require_staff),
    service: StoreManagerService = Depends(get_store_manager_service),
) -> StockResponse:
    return await service.get_product_inventory(
        store_id=store_id,
        product_id=product_id,
        user=current_user,
    )


@router.post(
    "/inventory/{product_id}/adjustments",
    response_model=StockAdjustmentResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform audited stock adjustment",
    description=(
        "Performs a transactional stock adjustment (INCREASE, DECREASE, or SET) with row locking. "
        "Strictly prevents negative stock and protects outstanding customer reservations. "
        "Sets transaction-local setting 'app.change_reason' to trigger automatic PostgreSQL audit logging. "
        "Emits transactional outbox event 'inventory.stock.updated' and 'inventory.low_stock' if threshold crossed."
    ),
)
async def adjust_stock(
    product_id: UUID,
    payload: StockAdjustmentRequest,
    store_id: UUID = Depends(resolve_manager_store_id),
    current_user: User = Depends(require_staff),
    service: StoreManagerService = Depends(get_store_manager_service),
    session: AsyncSession = Depends(get_db),
) -> StockAdjustmentResponse:
    adjustment = await service.adjust_stock(
        store_id=store_id,
        product_id=product_id,
        request=payload,
        user=current_user,
    )
    await session.commit()
    return adjustment


@router.get(
    "/inventory/{product_id}/history",
    response_model=List[InventoryAuditLogResponse],
    status_code=status.HTTP_200_OK,
    summary="Get inventory audit log history",
    description=(
        "Retrieves historical stock changes logged by PostgreSQL trigger 'inventory_audit'. "
        "Exposes product, store, previous and new on-hand/reserved quantities, reason, and timestamp."
    ),
)
async def get_inventory_audit_history(
    product_id: UUID,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    store_id: UUID = Depends(resolve_manager_store_id),
    current_user: User = Depends(require_staff),
    service: StoreManagerService = Depends(get_store_manager_service),
) -> List[InventoryAuditLogResponse]:
    history = await service.get_inventory_audit_history(
        store_id=store_id,
        product_id=product_id,
        user=current_user,
        skip=skip,
        limit=limit,
    )
    return [InventoryAuditLogResponse.model_validate(h) for h in history]
