"""
Store Manager domain service for SmartCart 2.0.
Coordinates store-scoped product management, Cloudinary image operations,
transactional row-locked stock adjustments, audit history, low-stock monitoring,
and atomic outbox event generation.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestError,
    DuplicateResourceError,
    ForbiddenError,
    NotFoundError,
    SmartCartError,
)
from app.models.enums import UserRole
from app.models.inventory import Inventory, InventoryAuditLog
from app.models.product import Product
from app.models.user import User
from app.repositories.inventory import InventoryRepository
from app.repositories.inventory_audit import InventoryAuditLogRepository
from app.repositories.product import ProductRepository
from app.schemas.inventory import StockResponse
from app.schemas.manager import (
    ManagerProductResponse,
    ProductCreateManagerRequest,
    ProductImageResponse,
    ProductUpdateManagerRequest,
    StockAdjustmentRequest,
    StockAdjustmentResponse,
    StockAdjustmentType,
)
from app.services.outbox import OutboxService
from app.services.storage import ImageStorageService


class StoreManagerService:
    """Domain service orchestrating store manager operations."""

    def __init__(
        self,
        product_repo: ProductRepository,
        inventory_repo: InventoryRepository,
        audit_repo: InventoryAuditLogRepository,
        outbox_service: OutboxService,
        storage_service: ImageStorageService,
        session: AsyncSession,
    ) -> None:
        self.product_repo = product_repo
        self.inventory_repo = inventory_repo
        self.audit_repo = audit_repo
        self.outbox_service = outbox_service
        self.storage_service = storage_service
        self.session = session

    def verify_store_authority(self, user: User, store_id: UUID) -> None:
        """
        Enforce strict store isolation:
        - STORE_MANAGER can ONLY manage their assigned_store_id.
        - ADMIN / SUPER_ADMIN can manage any store.
        - Other roles are rejected with ForbiddenError.
        """
        if user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            return

        if user.role == UserRole.STORE_MANAGER:
            if user.assigned_store_id is None or user.assigned_store_id != store_id:
                raise ForbiddenError(
                    f"Store manager is not authorized to manage store '{store_id}'"
                )
            return

        raise ForbiddenError(
            f"User role '{user.role.value}' is not authorized for store management operations"
        )

    def _extract_image_response(self, attributes: Dict[str, Any]) -> Optional[ProductImageResponse]:
        """Extract ProductImageResponse from product attributes JSONB."""
        image_data = attributes.get("image")
        if isinstance(image_data, dict) and "url" in image_data:
            return ProductImageResponse(
                url=image_data.get("url", ""),
                secure_url=image_data.get("secure_url"),
                public_id=image_data.get("public_id"),
                format=image_data.get("format"),
                width=image_data.get("width"),
                height=image_data.get("height"),
                bytes=image_data.get("bytes"),
            )
        return None

    def _to_manager_product_response(
        self,
        product: Product,
        inventory: Optional[Inventory] = None,
        store_id: Optional[UUID] = None,
    ) -> ManagerProductResponse:
        """Convert Product entity and optional Inventory to ManagerProductResponse."""
        qty_on_hand = inventory.qty_on_hand if inventory else None
        qty_reserved = inventory.qty_reserved if inventory else None
        qty_available = (
            max(0, inventory.qty_on_hand - inventory.qty_reserved) if inventory else None
        )
        low_stock_threshold = inventory.low_stock_threshold if inventory else None
        is_low_stock = (
            (qty_available <= low_stock_threshold)
            if (qty_available is not None and low_stock_threshold is not None)
            else None
        )

        return ManagerProductResponse(
            id=product.id,
            sku=product.sku,
            name=product.name,
            description=product.description,
            brand=product.brand,
            category=product.category,
            price_paise=product.price_paise,
            attributes=product.attributes or {},
            image=self._extract_image_response(product.attributes or {}),
            is_active=product.is_active,
            store_id=store_id or (inventory.store_id if inventory else None),
            qty_on_hand=qty_on_hand,
            qty_reserved=qty_reserved,
            qty_available=qty_available,
            low_stock_threshold=low_stock_threshold,
            is_low_stock=is_low_stock,
            created_at=product.created_at,
            updated_at=product.updated_at,
        )

    # =========================================================================
    # 1. Product Lifecycle Management
    # =========================================================================

    async def create_product(
        self,
        request: ProductCreateManagerRequest,
        store_id: UUID,
        user: User,
    ) -> ManagerProductResponse:
        """
        Create a new product in the catalogue and initialize stock for the store.
        Checks for SKU uniqueness and records transactional outbox events.
        """
        self.verify_store_authority(user, store_id)

        # SKU uniqueness check
        existing = await self.product_repo.get_by_sku(request.sku)
        if existing is not None:
            raise DuplicateResourceError(f"Product with SKU '{request.sku}' already exists")

        # 1. Create Product entity
        product = Product(
            sku=request.sku,
            name=request.name,
            description=request.description,
            brand=request.brand,
            category=request.category,
            price_paise=request.price_paise,
            attributes=request.attributes or {},
            is_active=True,
        )
        self.session.add(product)
        await self.session.flush()

        # 2. Initialize store inventory
        inventory = Inventory(
            store_id=store_id,
            product_id=product.id,
            qty_on_hand=request.initial_stock,
            qty_reserved=0,
            low_stock_threshold=request.low_stock_threshold,
        )
        self.session.add(inventory)
        await self.session.flush()

        # 3. Transactional Outbox Events
        await self.outbox_service.create_event(
            aggregate_type="product",
            aggregate_id=str(product.id),
            event_type="product.created",
            payload={
                "product_id": str(product.id),
                "sku": product.sku,
                "name": product.name,
                "brand": product.brand,
                "category": product.category,
                "price_paise": product.price_paise,
                "store_id": str(store_id),
                "initial_stock": request.initial_stock,
            },
        )

        if request.initial_stock > 0:
            await self.outbox_service.create_event(
                aggregate_type="inventory",
                aggregate_id=f"{store_id}:{product.id}",
                event_type="inventory.stock.updated",
                payload={
                    "store_id": str(store_id),
                    "product_id": str(product.id),
                    "qty_on_hand": request.initial_stock,
                    "qty_reserved": 0,
                    "qty_available": request.initial_stock,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        return self._to_manager_product_response(product, inventory, store_id)

    async def update_product(
        self,
        product_id: UUID,
        request: ProductUpdateManagerRequest,
        store_id: UUID,
        user: User,
    ) -> ManagerProductResponse:
        """
        Update product metadata.
        Strict Pricing Rule:
        Modifying 'price_paise' is strictly forbidden for STORE_MANAGER and only permitted
        for ADMIN / SUPER_ADMIN.
        """
        self.verify_store_authority(user, store_id)

        product = await self.product_repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError(f"Product with id '{product_id}' not found")

        # Strict pricing check
        if request.price_paise is not None:
            if user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
                raise ForbiddenError(
                    "Store managers cannot modify global catalog prices. "
                    "Price updates must be performed by a platform administrator."
                )
            product.price_paise = request.price_paise

        # Update metadata
        if request.name is not None:
            product.name = request.name
        if request.description is not None:
            product.description = request.description
        if request.brand is not None:
            product.brand = request.brand
        if request.category is not None:
            product.category = request.category
        if request.is_active is not None:
            product.is_active = request.is_active

        if request.attributes is not None:
            # Preserve existing image if attributes updated
            existing_image = (product.attributes or {}).get("image")
            new_attrs = dict(request.attributes)
            if existing_image and "image" not in new_attrs:
                new_attrs["image"] = existing_image
            product.attributes = new_attrs

        product.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        # Transactional outbox event
        await self.outbox_service.create_event(
            aggregate_type="product",
            aggregate_id=str(product.id),
            event_type="product.updated",
            payload={
                "product_id": str(product.id),
                "sku": product.sku,
                "name": product.name,
                "price_paise": product.price_paise,
                "is_active": product.is_active,
                "updated_at": product.updated_at.isoformat(),
            },
        )

        if request.is_active is False:
            await self.outbox_service.create_event(
                aggregate_type="product",
                aggregate_id=str(product.id),
                event_type="product.deactivated",
                payload={"product_id": str(product.id), "sku": product.sku},
            )

        inventory = await self.inventory_repo.get_stock(store_id, product.id)
        return self._to_manager_product_response(product, inventory, store_id)

    async def deactivate_product(
        self,
        product_id: UUID,
        store_id: UUID,
        user: User,
    ) -> ManagerProductResponse:
        """
        Perform safe product deactivation (soft delete).
        Preserves existing order references and relational integrity while removing
        the product from active catalog availability.
        """
        self.verify_store_authority(user, store_id)

        product = await self.product_repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError(f"Product with id '{product_id}' not found")

        if product.is_active:
            product.is_active = False
            product.updated_at = datetime.now(timezone.utc)
            await self.session.flush()

            await self.outbox_service.create_event(
                aggregate_type="product",
                aggregate_id=str(product.id),
                event_type="product.deactivated",
                payload={"product_id": str(product.id), "sku": product.sku},
            )

        inventory = await self.inventory_repo.get_stock(store_id, product.id)
        return self._to_manager_product_response(product, inventory, store_id)

    # =========================================================================
    # 2. Product Image Operations
    # =========================================================================

    async def upload_product_image(
        self,
        product_id: UUID,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        store_id: UUID,
        user: User,
    ) -> ManagerProductResponse:
        """
        Upload product image to Cloudinary and store metadata in product.attributes.
        If a previous image existed, deletes it from Cloudinary to prevent orphaned files.
        """
        self.verify_store_authority(user, store_id)

        product = await self.product_repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError(f"Product with id '{product_id}' not found")

        # Check for previous image to clean up
        prev_image = (product.attributes or {}).get("image")
        prev_public_id = prev_image.get("public_id") if isinstance(prev_image, dict) else None

        # Upload new image
        try:
            upload_result = await self.storage_service.upload_image(
                file_bytes=file_bytes,
                filename=filename,
                content_type=content_type,
            )
        except SmartCartError:
            raise
        except Exception as exc:
            raise SmartCartError(f"Cloudinary image upload failed: {str(exc)}") from exc

        # Update product attributes
        current_attrs = dict(product.attributes or {})
        current_attrs["image"] = upload_result
        product.attributes = current_attrs
        product.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        # Delete previous image from Cloudinary if replaced
        if prev_public_id and prev_public_id != upload_result.get("public_id"):
            await self.storage_service.delete_image(prev_public_id)

        # Emit outbox event
        await self.outbox_service.create_event(
            aggregate_type="product",
            aggregate_id=str(product.id),
            event_type="product.image.updated",
            payload={
                "product_id": str(product.id),
                "image_url": upload_result.get("url"),
                "public_id": upload_result.get("public_id"),
            },
        )

        inventory = await self.inventory_repo.get_stock(store_id, product.id)
        return self._to_manager_product_response(product, inventory, store_id)

    async def delete_product_image(
        self,
        product_id: UUID,
        store_id: UUID,
        user: User,
    ) -> ManagerProductResponse:
        """
        Delete product image from Cloudinary and remove from product attributes.
        """
        self.verify_store_authority(user, store_id)

        product = await self.product_repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError(f"Product with id '{product_id}' not found")

        current_attrs = dict(product.attributes or {})
        prev_image = current_attrs.pop("image", None)

        if prev_image and isinstance(prev_image, dict) and "public_id" in prev_image:
            await self.storage_service.delete_image(prev_image["public_id"])

        product.attributes = current_attrs
        product.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        await self.outbox_service.create_event(
            aggregate_type="product",
            aggregate_id=str(product.id),
            event_type="product.image.updated",
            payload={"product_id": str(product.id), "image_url": None},
        )

        inventory = await self.inventory_repo.get_stock(store_id, product.id)
        return self._to_manager_product_response(product, inventory, store_id)

    # =========================================================================
    # 3. Store Inventory & Stock Adjustments
    # =========================================================================

    async def adjust_stock(
        self,
        store_id: UUID,
        product_id: UUID,
        request: StockAdjustmentRequest,
        user: User,
    ) -> StockAdjustmentResponse:
        """
        Perform an atomic, concurrency-safe, audited stock adjustment.
        - Uses SELECT ... FOR UPDATE to prevent race conditions.
        - Prevents negative physical stock (qty_on_hand >= 0).
        - Protects outstanding reservations (new_on_hand >= qty_reserved).
        - Sets 'app.change_reason' to populate PostgreSQL inventory_audit_log via trigger.
        - Emits 'inventory.stock.updated' and 'inventory.low_stock' outbox events.
        """
        self.verify_store_authority(user, store_id)

        # Verify product existence
        product = await self.product_repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError(f"Product with id '{product_id}' not found")

        # Concurrency Lock: Row-level lock on inventory record
        stmt = (
            select(Inventory)
            .where(Inventory.store_id == store_id, Inventory.product_id == product_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        inventory = result.scalar_one_or_none()

        if inventory is None:
            if request.adjustment_type == StockAdjustmentType.DECREASE:
                raise BadRequestError(
                    f"Cannot decrease stock: No inventory record exists for product '{product_id}' in store '{store_id}'"
                )
            # Create initial inventory record
            inventory = Inventory(
                store_id=store_id,
                product_id=product_id,
                qty_on_hand=0,
                qty_reserved=0,
                low_stock_threshold=request.low_stock_threshold or 5,
            )
            self.session.add(inventory)
            await self.session.flush()

        old_on_hand = inventory.qty_on_hand
        qty_reserved = inventory.qty_reserved
        old_available = max(0, old_on_hand - qty_reserved)

        # Calculate new quantity based on adjustment type
        if request.adjustment_type == StockAdjustmentType.INCREASE:
            new_on_hand = old_on_hand + request.quantity
            quantity_delta = request.quantity
        elif request.adjustment_type == StockAdjustmentType.DECREASE:
            new_on_hand = old_on_hand - request.quantity
            quantity_delta = -request.quantity
        elif request.adjustment_type == StockAdjustmentType.SET:
            new_on_hand = request.quantity
            quantity_delta = new_on_hand - old_on_hand
        else:
            raise BadRequestError(f"Invalid adjustment type: {request.adjustment_type}")

        # Invariant 1: Physical stock cannot be negative
        if new_on_hand < 0:
            raise BadRequestError(
                f"Adjustment would result in negative physical stock ({new_on_hand}). Operation rejected."
            )

        # Invariant 2: Cannot reduce stock below currently active reservations
        if new_on_hand < qty_reserved:
            raise BadRequestError(
                f"Cannot adjust stock to {new_on_hand} units; {qty_reserved} units are currently "
                f"reserved for customer orders or active carts. Minimum allowable stock is {qty_reserved}."
            )

        # Trigger Audit Reason Setup
        audit_reason = f"{request.adjustment_type.value}: {request.reason} [user:{user.id}]"
        await self.session.execute(
            text("SELECT set_config('app.change_reason', :reason, true)"),
            {"reason": audit_reason},
        )

        # Apply update
        inventory.qty_on_hand = new_on_hand
        if request.low_stock_threshold is not None:
            inventory.low_stock_threshold = request.low_stock_threshold
        inventory.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        new_available = new_on_hand - qty_reserved
        is_low_stock = new_available <= inventory.low_stock_threshold
        was_low_stock = old_available <= inventory.low_stock_threshold

        # Transactional outbox event: stock updated
        await self.outbox_service.create_event(
            aggregate_type="inventory",
            aggregate_id=f"{store_id}:{product_id}",
            event_type="inventory.stock.updated",
            payload={
                "store_id": str(store_id),
                "product_id": str(product_id),
                "old_on_hand": old_on_hand,
                "new_on_hand": new_on_hand,
                "qty_reserved": qty_reserved,
                "qty_available": new_available,
                "adjustment_type": request.adjustment_type.value,
                "reason": request.reason,
                "updated_at": inventory.updated_at.isoformat(),
            },
        )

        # Transactional outbox event: low stock alert (suppress duplicate alert if was already low)
        if is_low_stock and not was_low_stock:
            await self.outbox_service.create_event(
                aggregate_type="inventory",
                aggregate_id=f"{store_id}:{product_id}",
                event_type="inventory.low_stock",
                payload={
                    "store_id": str(store_id),
                    "product_id": str(product_id),
                    "product_name": product.name,
                    "qty_available": new_available,
                    "threshold": inventory.low_stock_threshold,
                    "alert_at": datetime.now(timezone.utc).isoformat(),
                },
            )

        return StockAdjustmentResponse(
            store_id=store_id,
            product_id=product_id,
            old_on_hand=old_on_hand,
            new_on_hand=new_on_hand,
            qty_reserved=qty_reserved,
            qty_available=new_available,
            adjustment_type=request.adjustment_type,
            quantity_delta=quantity_delta,
            reason=request.reason,
            low_stock_threshold=inventory.low_stock_threshold,
            is_low_stock=is_low_stock,
            updated_at=inventory.updated_at,
        )

    # =========================================================================
    # 4. Inventory Views & Low-Stock Monitoring
    # =========================================================================

    async def get_store_inventory(
        self,
        store_id: UUID,
        user: User,
        skip: int = 0,
        limit: int = 100,
    ) -> List[StockResponse]:
        """List inventory records for the specified store with pagination."""
        self.verify_store_authority(user, store_id)
        records = await self.inventory_repo.list_by_store(store_id, skip=skip, limit=limit)
        return [
            StockResponse(
                store_id=r.store_id,
                product_id=r.product_id,
                qty_on_hand=r.qty_on_hand,
                qty_reserved=r.qty_reserved,
                qty_available=max(0, r.qty_on_hand - r.qty_reserved),
                low_stock_threshold=r.low_stock_threshold,
                is_low_stock=(r.qty_on_hand - r.qty_reserved) <= r.low_stock_threshold,
                updated_at=r.updated_at,
            )
            for r in records
        ]

    async def get_low_stock_items(
        self,
        store_id: UUID,
        user: User,
    ) -> List[StockResponse]:
        """List inventory items at or below their low-stock threshold for the store."""
        self.verify_store_authority(user, store_id)
        records = await self.inventory_repo.list_low_stock(store_id=store_id)
        return [
            StockResponse(
                store_id=r.store_id,
                product_id=r.product_id,
                qty_on_hand=r.qty_on_hand,
                qty_reserved=r.qty_reserved,
                qty_available=max(0, r.qty_on_hand - r.qty_reserved),
                low_stock_threshold=r.low_stock_threshold,
                is_low_stock=True,
                updated_at=r.updated_at,
            )
            for r in records
        ]

    async def get_product_inventory(
        self,
        store_id: UUID,
        product_id: UUID,
        user: User,
    ) -> StockResponse:
        """Get inventory status for a specific product at the store."""
        self.verify_store_authority(user, store_id)
        stock = await self.inventory_repo.get_stock(store_id, product_id)
        if stock is None:
            raise NotFoundError(
                f"Inventory record for product '{product_id}' at store '{store_id}' not found"
            )
        qty_available = max(0, stock.qty_on_hand - stock.qty_reserved)
        return StockResponse(
            store_id=stock.store_id,
            product_id=stock.product_id,
            qty_on_hand=stock.qty_on_hand,
            qty_reserved=stock.qty_reserved,
            qty_available=qty_available,
            low_stock_threshold=stock.low_stock_threshold,
            is_low_stock=qty_available <= stock.low_stock_threshold,
            updated_at=stock.updated_at,
        )

    async def get_inventory_audit_history(
        self,
        store_id: UUID,
        product_id: UUID,
        user: User,
        skip: int = 0,
        limit: int = 50,
    ) -> Sequence[InventoryAuditLog]:
        """Retrieve audit history for a store product, ordered newest first."""
        self.verify_store_authority(user, store_id)
        return await self.audit_repo.list_by_store_and_product(
            store_id=store_id,
            product_id=product_id,
            skip=skip,
            limit=limit,
        )

    async def list_products(
        self,
        store_id: UUID,
        user: User,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        is_active: Optional[bool] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[ManagerProductResponse]:
        """List products with store-specific inventory status for the manager."""
        self.verify_store_authority(user, store_id)

        stmt = select(Product)
        if is_active is not None:
            stmt = stmt.where(Product.is_active == is_active)
        if category:
            stmt = stmt.where(Product.category == category)
        if brand:
            stmt = stmt.where(Product.brand == brand)
        stmt = stmt.order_by(Product.name).offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        products = result.scalars().all()

        responses: List[ManagerProductResponse] = []
        for p in products:
            inv = await self.inventory_repo.get_stock(store_id, p.id)
            responses.append(self._to_manager_product_response(p, inv, store_id))

        return responses

    async def get_product_detail(
        self,
        product_id: UUID,
        store_id: UUID,
        user: User,
    ) -> ManagerProductResponse:
        """Get product detail including image and store-specific inventory status."""
        self.verify_store_authority(user, store_id)

        product = await self.product_repo.get_by_id(product_id)
        if product is None:
            raise NotFoundError(f"Product with id '{product_id}' not found")

        inv = await self.inventory_repo.get_stock(store_id, product.id)
        return self._to_manager_product_response(product, inv, store_id)
