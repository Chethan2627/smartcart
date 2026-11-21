"""
Kafka to OpenSearch event synchronization service for SmartCart 2.0.
Listens to smartcart.products and smartcart.inventory Kafka topics,
reads authoritative state from PostgreSQL, enforces stale-update guards,
and projects search document updates into OpenSearch.
"""
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.kafka.consumer import SmartCartKafkaConsumer
from app.kafka.schemas import SmartCartEvent
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.store import Store
from app.opensearch.indexing import ProductIndexService

logger = logging.getLogger("smartcart.opensearch.sync")


class OpenSearchSyncService:
    """
    Event-driven synchronization service projecting PostgreSQL mutations into OpenSearch.
    Maintains PostgreSQL as the single source of truth.
    """

    def __init__(self, index_service: Optional[ProductIndexService] = None) -> None:
        self.index_service: ProductIndexService = index_service or ProductIndexService()

    async def sync_product_from_db(
        self,
        product_id: UUID,
        store_id: Optional[UUID],
        session: AsyncSession,
        refresh: bool = False,
    ) -> int:
        """
        Fetch canonical product and inventory state directly from PostgreSQL and index into OpenSearch.
        Returns the number of store-product documents created or updated.
        """
        # 1. Fetch authoritative product
        prod_stmt = select(Product).where(Product.id == product_id)
        prod_res = await session.execute(prod_stmt)
        product = prod_res.scalar_one_or_none()
        if product is None:
            logger.warning("Product id=%s not found in PostgreSQL. Skipping OpenSearch sync.", product_id)
            return 0

        # Extract image URL from attributes JSONB
        attrs = product.attributes or {}
        image_url = None
        if isinstance(attrs, dict):
            img_data = attrs.get("image")
            if isinstance(img_data, dict):
                image_url = img_data.get("secure_url") or img_data.get("url")
            if not image_url:
                image_url = attrs.get("image_url")

        # 2. Fetch authoritative inventory records
        inv_stmt = select(Inventory).where(Inventory.product_id == product_id)
        if store_id is not None:
            inv_stmt = inv_stmt.where(Inventory.store_id == store_id)
        inv_res = await session.execute(inv_stmt)
        inventories: List[Inventory] = list(inv_res.scalars().all())

        # If product has no inventory rows yet, check if store_id was passed
        if not inventories and store_id is not None:
            # Create a 0-stock document for this store
            doc = {
                "product_id": str(product.id),
                "store_id": str(store_id),
                "sku": product.sku,
                "name": product.name,
                "brand": product.brand,
                "category": product.category,
                "description": product.description,
                "price_paise": int(product.price_paise),
                "image_url": image_url,
                "is_active": product.is_active,
                "qty_on_hand": 0,
                "qty_reserved": 0,
                "qty_available": 0,
                "is_in_stock": False,
                "low_stock_threshold": 5,
                "created_at": product.created_at.isoformat() if product.created_at else None,
                "updated_at": product.updated_at.isoformat() if product.updated_at else None,
            }
            self.index_service.index_store_product(doc, refresh=refresh)
            return 1

        indexed_count = 0
        for inv in inventories:
            qty_avail = max(0, inv.qty_on_hand - inv.qty_reserved)
            latest_updated = max(
                inv.updated_at or datetime.now(timezone.utc),
                product.updated_at or datetime.now(timezone.utc),
            )
            doc = {
                "product_id": str(product.id),
                "store_id": str(inv.store_id),
                "sku": product.sku,
                "name": product.name,
                "brand": product.brand,
                "category": product.category,
                "description": product.description,
                "price_paise": int(product.price_paise),
                "image_url": image_url,
                "is_active": product.is_active,
                "qty_on_hand": int(inv.qty_on_hand),
                "qty_reserved": int(inv.qty_reserved),
                "qty_available": qty_avail,
                "is_in_stock": qty_avail > 0,
                "low_stock_threshold": int(inv.low_stock_threshold),
                "created_at": product.created_at.isoformat() if product.created_at else None,
                "updated_at": latest_updated.isoformat(),
            }
            self.index_service.index_store_product(doc, refresh=refresh)
            indexed_count += 1

        logger.info(
            "Synchronized %d store-product documents for product_id=%s from PostgreSQL into OpenSearch",
            indexed_count,
            product_id,
        )
        return indexed_count

    async def sync_inventory_from_db(
        self,
        product_id: UUID,
        store_id: UUID,
        session: AsyncSession,
        refresh: bool = False,
    ) -> bool:
        """
        Query authoritative inventory row from PostgreSQL and update the OpenSearch store-product document.
        Guards against stale overwrites using the authoritative PostgreSQL updated_at timestamp.
        """
        inv_stmt = select(Inventory).where(
            Inventory.product_id == product_id,
            Inventory.store_id == store_id,
        )
        inv_res = await session.execute(inv_stmt)
        inventory = inv_res.scalar_one_or_none()
        if inventory is None:
            logger.warning(
                "Authoritative inventory not found in PostgreSQL for store_id=%s, product_id=%s. Skipping OpenSearch sync.",
                store_id,
                product_id,
            )
            return False

        # Attempt atomic stock update
        updated = self.index_service.update_stock(
            product_id=product_id,
            store_id=store_id,
            qty_on_hand=inventory.qty_on_hand,
            qty_reserved=inventory.qty_reserved,
            updated_at=inventory.updated_at,
            refresh=refresh,
        )

        # If document did not exist yet in OpenSearch, perform full product-store sync
        if not updated:
            existing = self.index_service.get_document(product_id, store_id)
            if existing is None:
                logger.info(
                    "Document %s_%s does not exist in OpenSearch. Performing full snapshot sync from PostgreSQL.",
                    product_id,
                    store_id,
                )
                await self.sync_product_from_db(product_id, store_id, session, refresh=refresh)
                return True

        return updated

    # ---------------- Kafka Event Handlers ----------------

    async def handle_product_created(self, event: SmartCartEvent, session: AsyncSession) -> None:
        """Handle product.created event by indexing authoritative product into OpenSearch."""
        raw_pid = event.payload.get("product_id")
        raw_sid = event.payload.get("store_id")
        if not raw_pid:
            logger.error("Missing product_id in product.created payload: %s", event.payload)
            return

        product_id = UUID(str(raw_pid))
        store_id = UUID(str(raw_sid)) if raw_sid else None
        await self.sync_product_from_db(product_id, store_id, session)

    async def handle_product_updated(self, event: SmartCartEvent, session: AsyncSession) -> None:
        """Handle product.updated event by refreshing catalog metadata from PostgreSQL."""
        raw_pid = event.payload.get("product_id")
        if not raw_pid:
            logger.error("Missing product_id in product.updated payload: %s", event.payload)
            return

        product_id = UUID(str(raw_pid))
        await self.sync_product_from_db(product_id, None, session)

    async def handle_product_deactivated(self, event: SmartCartEvent, session: AsyncSession) -> None:
        """Handle product.deactivated event by marking is_active=false across all store documents."""
        raw_pid = event.payload.get("product_id")
        if not raw_pid:
            logger.error("Missing product_id in product.deactivated payload: %s", event.payload)
            return

        product_id = UUID(str(raw_pid))
        self.index_service.deactivate_product(product_id)

    async def handle_product_image_updated(self, event: SmartCartEvent, session: AsyncSession) -> None:
        """Handle product.image.updated event by updating image_url across all store documents."""
        raw_pid = event.payload.get("product_id")
        image_url = event.payload.get("image_url")
        if not raw_pid:
            logger.error("Missing product_id in product.image.updated payload: %s", event.payload)
            return

        product_id = UUID(str(raw_pid))
        self.index_service.update_product_metadata(
            product_id=product_id,
            updates={
                "image_url": image_url,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    async def handle_inventory_stock_updated(self, event: SmartCartEvent, session: AsyncSession) -> None:
        """
        Handle inventory.stock.updated / inventory.changed event.
        Fetches authoritative current inventory from PostgreSQL and updates the store-product document.
        """
        raw_pid = event.payload.get("product_id")
        raw_sid = event.payload.get("store_id")
        if not raw_pid or not raw_sid:
            logger.error("Missing product_id or store_id in inventory stock event: %s", event.payload)
            return

        product_id = UUID(str(raw_pid))
        store_id = UUID(str(raw_sid))
        await self.sync_inventory_from_db(product_id, store_id, session)

    async def handle_inventory_low_stock(self, event: SmartCartEvent, session: AsyncSession) -> None:
        """Handle inventory.low_stock event by ensuring OpenSearch reflects authoritative stock."""
        raw_pid = event.payload.get("product_id")
        raw_sid = event.payload.get("store_id")
        if raw_pid and raw_sid:
            await self.sync_inventory_from_db(UUID(str(raw_pid)), UUID(str(raw_sid)), session)


def register_opensearch_handlers(
    consumer: SmartCartKafkaConsumer,
    sync_service: Optional[OpenSearchSyncService] = None,
) -> None:
    """
    Register OpenSearch synchronization handlers onto an existing SmartCartKafkaConsumer.
    Preserves all existing deduplication, transaction handling, and DLQ behavior.
    """
    service = sync_service or OpenSearchSyncService()

    consumer.register_handler("product.created", service.handle_product_created)
    consumer.register_handler("product.updated", service.handle_product_updated)
    consumer.register_handler("product.deactivated", service.handle_product_deactivated)
    consumer.register_handler("product.image.updated", service.handle_product_image_updated)
    consumer.register_handler("inventory.stock.updated", service.handle_inventory_stock_updated)
    consumer.register_handler("inventory.changed", service.handle_inventory_stock_updated)
    consumer.register_handler("inventory.low_stock", service.handle_inventory_low_stock)

    logger.info("Successfully registered OpenSearch sync handlers with Kafka consumer.")
