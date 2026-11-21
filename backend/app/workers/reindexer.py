"""
Zero-downtime OpenSearch Reindexer CLI for SmartCart 2.0.
Streams products and store inventory from authoritative PostgreSQL into versioned OpenSearch indexes
and performs atomic alias switching.

Usage:
    python -m app.workers.reindexer --create-index
    python -m app.workers.reindexer --bulk-index
    python -m app.workers.reindexer --reindex-all
    python -m app.workers.reindexer --status
"""
import argparse
import asyncio
from datetime import datetime, timezone
import logging
import sys
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_maker
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.store import Store
from app.opensearch.client import check_opensearch_health, get_opensearch_client
from app.opensearch.config import OpenSearchConfigBuilder
from app.opensearch.indexing import ProductIndexService
from app.opensearch.mappings import get_product_index_mapping

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("smartcart.workers.reindexer")


async def fetch_all_store_product_documents(session: AsyncSession) -> List[Dict[str, Any]]:
    """
    Fetch all active stores and active products with their current store inventory from PostgreSQL.
    Returns list of store-product document dictionaries.
    """
    # 1. Fetch all active stores
    store_stmt = select(Store).where(Store.is_active == True)
    store_res = await session.execute(store_stmt)
    stores = {s.id: s for s in store_res.scalars().all()}
    if not stores:
        logger.warning("No active stores found in PostgreSQL database.")

    # 2. Fetch all products
    prod_stmt = select(Product)
    prod_res = await session.execute(prod_stmt)
    products = {p.id: p for p in prod_res.scalars().all()}

    # 3. Fetch all inventory records
    inv_stmt = select(Inventory)
    inv_res = await session.execute(inv_stmt)
    inventories = inv_res.scalars().all()

    documents: List[Dict[str, Any]] = []

    # Map inventory by (product_id, store_id)
    inv_map = {(inv.product_id, inv.store_id): inv for inv in inventories}

    for (product_id, store_id), inv in inv_map.items():
        prod = products.get(product_id)
        if not prod:
            continue

        # Extract image URL
        image_url = None
        attrs = prod.attributes or {}
        if isinstance(attrs, dict):
            img_data = attrs.get("image")
            if isinstance(img_data, dict):
                image_url = img_data.get("secure_url") or img_data.get("url")
            if not image_url:
                image_url = attrs.get("image_url")

        qty_avail = max(0, inv.qty_on_hand - inv.qty_reserved)
        latest_updated = max(
            inv.updated_at or datetime.now(timezone.utc),
            prod.updated_at or datetime.now(timezone.utc),
        )

        doc = {
            "product_id": str(prod.id),
            "store_id": str(store_id),
            "sku": prod.sku,
            "name": prod.name,
            "brand": prod.brand,
            "category": prod.category,
            "description": prod.description,
            "price_paise": int(prod.price_paise),
            "image_url": image_url,
            "is_active": prod.is_active,
            "qty_on_hand": int(inv.qty_on_hand),
            "qty_reserved": int(inv.qty_reserved),
            "qty_available": qty_avail,
            "is_in_stock": qty_avail > 0,
            "low_stock_threshold": int(inv.low_stock_threshold),
            "created_at": prod.created_at.isoformat() if prod.created_at else None,
            "updated_at": latest_updated.isoformat(),
        }
        documents.append(doc)

    logger.info(
        "Extracted %d store-product documents across %d stores and %d products from PostgreSQL.",
        len(documents),
        len(stores),
        len(products),
    )
    return documents


async def create_versioned_index(index_service: ProductIndexService, index_name: Optional[str] = None) -> str:
    """Create a new versioned index using current mappings."""
    target_index = index_name or f"{OpenSearchConfigBuilder.get_index_alias()}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    logger.info("Creating index '%s'...", target_index)
    index_service.ensure_index(index_name=target_index)
    return target_index


async def bulk_index_from_postgres(
    index_service: ProductIndexService,
    target_index: Optional[str] = None,
    chunk_size: int = 500,
) -> int:
    """Read all authoritative store-product rows from PostgreSQL and stream into OpenSearch."""
    idx_name = target_index or index_service.index_name
    service = ProductIndexService(client=index_service.client, index_name=idx_name)

    async with async_session_maker() as session:
        docs = await fetch_all_store_product_documents(session)

    if not docs:
        logger.info("No documents found in PostgreSQL to index.")
        return 0

    success_count, errors = service.bulk_index_documents(docs, chunk_size=chunk_size, refresh=True)
    if errors:
        logger.warning("Encountered %d errors during bulk indexing", len(errors))
    return success_count


async def run_reindex_all(chunk_size: int = 500) -> None:
    """
    Perform a complete zero-downtime reindexing:
    1. Create timestamped index (e.g. smartcart_products_YYYYMMDD_HHMMSS)
    2. Bulk index all documents from PostgreSQL
    3. Atomically switch search alias to new index
    """
    logger.info("Starting complete zero-downtime reindexing pipeline...")
    service = ProductIndexService()
    alias = OpenSearchConfigBuilder.get_index_alias()

    # 1. Create new index
    new_index_name = await create_versioned_index(service)
    logger.info("New index '%s' created successfully.", new_index_name)

    # 2. Bulk index into new index
    total_indexed = await bulk_index_from_postgres(service, target_index=new_index_name, chunk_size=chunk_size)
    logger.info("Successfully indexed %d documents into '%s'.", total_indexed, new_index_name)

    # 3. Atomically switch alias
    service.swap_alias(new_index=new_index_name, alias=alias)
    logger.info("Zero-downtime reindexing complete! Alias '%s' now serves '%s'.", alias, new_index_name)


def print_status() -> None:
    """Print current cluster health and index stats."""
    client = get_opensearch_client()
    health = check_opensearch_health(client)
    alias = OpenSearchConfigBuilder.get_index_alias()
    service = ProductIndexService(client=client, index_name=alias)
    stats = service.get_index_stats()

    print("\n--- OpenSearch Cluster Status ---")
    for k, v in health.items():
        print(f"  {k}: {v}")

    print("\n--- Index & Alias Stats ---")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print("---------------------------------\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SmartCart 2.0 OpenSearch Reindexer CLI")
    parser.add_argument("--create-index", action="store_true", help="Create new versioned index with schema mappings")
    parser.add_argument("--bulk-index", action="store_true", help="Stream all products from PostgreSQL into OpenSearch")
    parser.add_argument("--reindex-all", action="store_true", help="Zero-downtime reindex: create, bulk index, and swap alias")
    parser.add_argument("--status", action="store_true", help="Display OpenSearch cluster and index status")
    parser.add_argument("--index-name", type=str, default=None, help="Target index name (optional)")
    parser.add_argument("--chunk-size", type=int, default=500, help="Bulk indexing chunk size (default: 500)")
    return parser.parse_args()


async def main_async(args: argparse.Namespace) -> None:
    service = ProductIndexService()

    if args.status:
        print_status()
    elif args.create_index:
        idx = await create_versioned_index(service, args.index_name)
        print(f"Index created: {idx}")
    elif args.bulk_index:
        count = await bulk_index_from_postgres(service, target_index=args.index_name, chunk_size=args.chunk_size)
        print(f"Bulk indexed {count} documents.")
    elif args.reindex_all:
        await run_reindex_all(chunk_size=args.chunk_size)
    else:
        print("Please specify an action: --create-index, --bulk-index, --reindex-all, or --status")


def main() -> None:
    args = parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
