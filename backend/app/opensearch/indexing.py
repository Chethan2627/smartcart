"""
OpenSearch indexing service for SmartCart 2.0.
Manages index creation, document indexing, stock updates with stale-update protection,
product catalog synchronization, bulk streaming, and atomic alias switching.
"""
from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from opensearchpy import OpenSearch, helpers
from opensearchpy.exceptions import NotFoundError, OpenSearchException

from app.config import settings
from app.opensearch.client import get_opensearch_client
from app.opensearch.config import OpenSearchConfigBuilder
from app.opensearch.mappings import build_store_product_doc_id, get_product_index_mapping

logger = logging.getLogger("smartcart.opensearch.indexing")


class ProductIndexService:
    """Service responsible for indexing and synchronizing products into OpenSearch."""

    def __init__(
        self,
        client: Optional[OpenSearch] = None,
        index_name: Optional[str] = None,
    ) -> None:
        self.client: OpenSearch = client or get_opensearch_client()
        self.index_name: str = index_name or OpenSearchConfigBuilder.get_index_alias()

    def ensure_index(
        self,
        index_name: Optional[str] = None,
        alias: Optional[str] = None,
    ) -> bool:
        """
        Create the versioned product search index if it does not already exist.
        Optionally binds the provided alias atomically.
        """
        target_index = index_name or OpenSearchConfigBuilder.get_versioned_index_name()
        target_alias = alias or OpenSearchConfigBuilder.get_index_alias()

        try:
            if not self.client.indices.exists(index=target_index):
                replicas = None
                try:
                    cluster_health = self.client.cluster.health()
                    data_nodes = cluster_health.get("number_of_data_nodes", cluster_health.get("number_of_nodes", 1))
                    if data_nodes <= 1:
                        replicas = 0
                except Exception as ex:
                    logger.debug("Could not inspect cluster data nodes: %s", ex)

                mapping = get_product_index_mapping(number_of_replicas=replicas)
                logger.info("Creating OpenSearch index '%s' with mappings (replicas=%s)...", target_index, replicas)
                self.client.indices.create(index=target_index, body=mapping)

            if target_alias:
                # Ensure alias points to target_index
                alias_exists = self.client.indices.exists_alias(name=target_alias)
                if not alias_exists:
                    logger.info("Binding alias '%s' -> '%s'", target_alias, target_index)
                    self.client.indices.put_alias(index=target_index, name=target_alias)

            return True
        except OpenSearchException as exc:
            logger.error("Failed to ensure OpenSearch index '%s': %s", target_index, exc)
            raise

    def refresh_index(self, index_name: Optional[str] = None) -> None:
        """Explicitly refresh the index to make recent operations searchable."""
        target = index_name or self.index_name
        try:
            self.client.indices.refresh(index=target)
        except Exception as exc:
            logger.warning("Index refresh encountered notice on '%s': %s", target, exc)

    def index_store_product(
        self,
        doc: Dict[str, Any],
        refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Index or fully replace a store-product document in OpenSearch.
        The document ID is deterministically set to {product_id}_{store_id}.
        """
        product_id = str(doc["product_id"])
        store_id = str(doc["store_id"])
        doc_id = build_store_product_doc_id(product_id, store_id)

        # Normalize dates
        normalized_doc = dict(doc)
        normalized_doc["id"] = doc_id
        normalized_doc["product_id"] = product_id
        normalized_doc["store_id"] = store_id

        # Calculate derived available stock
        qty_on_hand = int(normalized_doc.get("qty_on_hand", 0))
        qty_reserved = int(normalized_doc.get("qty_reserved", 0))
        qty_available = max(0, qty_on_hand - qty_reserved)
        normalized_doc["qty_available"] = qty_available
        normalized_doc["is_in_stock"] = qty_available > 0

        logger.debug("Indexing store-product document id=%s in index=%s", doc_id, self.index_name)
        response = self.client.index(
            index=self.index_name,
            id=doc_id,
            body=normalized_doc,
            refresh=refresh,
        )
        return response

    def get_document(self, product_id: Any, store_id: Any) -> Optional[Dict[str, Any]]:
        """Retrieve a store-product document by its composite ID."""
        doc_id = build_store_product_doc_id(product_id, store_id)
        try:
            resp = self.client.get(index=self.index_name, id=doc_id)
            return resp.get("_source")
        except NotFoundError:
            return None
        except OpenSearchException as exc:
            logger.error("Error retrieving document id=%s: %s", doc_id, exc)
            return None

    def delete_document(self, product_id: Any, store_id: Any, refresh: bool = False) -> bool:
        """Delete a store-product document by its composite ID."""
        doc_id = build_store_product_doc_id(product_id, store_id)
        try:
            self.client.delete(index=self.index_name, id=doc_id, refresh=refresh)
            logger.debug("Deleted document id=%s from index=%s", doc_id, self.index_name)
            return True
        except NotFoundError:
            return False
        except OpenSearchException as exc:
            logger.error("Error deleting document id=%s: %s", doc_id, exc)
            return False

    def update_stock(
        self,
        product_id: Any,
        store_id: Any,
        qty_on_hand: int,
        qty_reserved: int,
        updated_at: Any,
        refresh: bool = False,
    ) -> bool:
        """
        Update inventory stock fields for a specific store-product document.
        Guards against stale updates by checking whether the document's indexed
        timestamp is already newer than the provided updated_at.
        """
        doc_id = build_store_product_doc_id(product_id, store_id)
        existing = self.get_document(product_id, store_id)

        if existing is None:
            logger.warning(
                "Document id=%s not found in OpenSearch index=%s. Cannot perform stock update.",
                doc_id,
                self.index_name,
            )
            return False

        # Stale-update protection
        existing_updated_at_str = existing.get("updated_at")
        if existing_updated_at_str and updated_at:
            try:
                if isinstance(updated_at, str):
                    new_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                elif isinstance(updated_at, datetime):
                    new_dt = updated_at
                else:
                    new_dt = None

                if new_dt is not None:
                    if new_dt.tzinfo is None:
                        new_dt = new_dt.replace(tzinfo=timezone.utc)
                    existing_dt = datetime.fromisoformat(existing_updated_at_str.replace("Z", "+00:00"))
                    if existing_dt.tzinfo is None:
                        existing_dt = existing_dt.replace(tzinfo=timezone.utc)

                    if existing_dt > new_dt:
                        logger.info(
                            "Skipping stale stock update for id=%s (current_doc_time=%s > event_time=%s)",
                            doc_id,
                            existing_dt.isoformat(),
                            new_dt.isoformat(),
                        )
                        return False
            except Exception as parse_exc:
                logger.warning("Timestamp comparison warning for id=%s: %s", doc_id, parse_exc)

        qty_available = max(0, int(qty_on_hand) - int(qty_reserved))
        is_in_stock = qty_available > 0
        iso_updated_at = updated_at.isoformat() if hasattr(updated_at, "isoformat") else str(updated_at)

        update_body = {
            "doc": {
                "qty_on_hand": int(qty_on_hand),
                "qty_reserved": int(qty_reserved),
                "qty_available": qty_available,
                "is_in_stock": is_in_stock,
                "updated_at": iso_updated_at,
            }
        }

        try:
            self.client.update(
                index=self.index_name,
                id=doc_id,
                body=update_body,
                refresh=refresh,
            )
            logger.debug("Successfully updated stock for document id=%s", doc_id)
            return True
        except NotFoundError:
            logger.warning("Document id=%s not found during update call.", doc_id)
            return False
        except OpenSearchException as exc:
            logger.error("Failed to update stock for document id=%s: %s", doc_id, exc)
            raise

    def update_product_metadata(
        self,
        product_id: Any,
        updates: Dict[str, Any],
        refresh: bool = False,
    ) -> int:
        """
        Update catalog metadata (name, sku, brand, category, price, image_url, is_active)
        across all store documents matching product_id.
        """
        pid_str = str(product_id)
        logger.info("Propagating product metadata updates for product_id=%s across all stores", pid_str)

        # Build inline Painless script
        script_parts = []
        params = {}
        for key, value in updates.items():
            if key in ("name", "sku", "brand", "category", "description", "price_paise", "image_url", "is_active", "updated_at"):
                script_parts.append(f"ctx._source.{key} = params.{key}")
                params[key] = value

        if not script_parts:
            logger.debug("No valid catalog update fields provided for product_id=%s", pid_str)
            return 0

        script_code = "; ".join(script_parts) + ";"
        query_body = {
            "query": {
                "term": {"product_id": pid_str}
            },
            "script": {
                "source": script_code,
                "lang": "painless",
                "params": params,
            },
        }

        try:
            resp = self.client.update_by_query(
                index=self.index_name,
                body=query_body,
                refresh=refresh,
                conflicts="proceed",
            )
            updated_count = resp.get("updated", 0)
            logger.info("Updated %d store documents for product_id=%s", updated_count, pid_str)
            return updated_count
        except OpenSearchException as exc:
            logger.error("Error executing update_by_query for product_id=%s: %s", pid_str, exc)
            raise

    def deactivate_product(self, product_id: Any, refresh: bool = False) -> int:
        """Set is_active=false across all store documents matching product_id."""
        return self.update_product_metadata(
            product_id=product_id,
            updates={"is_active": False, "updated_at": datetime.now(timezone.utc).isoformat()},
            refresh=refresh,
        )

    def bulk_index_documents(
        self,
        documents: List[Dict[str, Any]],
        chunk_size: int = 500,
        refresh: bool = False,
    ) -> Tuple[int, List[Any]]:
        """
        Bulk index store-product documents using opensearchpy.helpers.bulk.
        Automatically injects _index and _id for each document.
        """
        if not documents:
            return 0, []

        actions = []
        for doc in documents:
            doc_copy = dict(doc)
            product_id = str(doc_copy["product_id"])
            store_id = str(doc_copy["store_id"])
            doc_id = build_store_product_doc_id(product_id, store_id)

            qty_on_hand = int(doc_copy.get("qty_on_hand", 0))
            qty_reserved = int(doc_copy.get("qty_reserved", 0))
            qty_available = max(0, qty_on_hand - qty_reserved)
            doc_copy["id"] = doc_id
            doc_copy["product_id"] = product_id
            doc_copy["store_id"] = store_id
            doc_copy["qty_available"] = qty_available
            doc_copy["is_in_stock"] = qty_available > 0

            actions.append({
                "_index": self.index_name,
                "_id": doc_id,
                "_source": doc_copy,
            })

        logger.info("Bulk indexing %d store-product documents into '%s'...", len(actions), self.index_name)
        success_count, errors = helpers.bulk(
            self.client,
            actions,
            chunk_size=chunk_size,
            refresh=refresh,
            raise_on_error=False,
        )
        logger.info("Bulk index completed: %d indexed, %d errors", success_count, len(errors))
        return success_count, errors

    def swap_alias(
        self,
        new_index: str,
        alias: Optional[str] = None,
    ) -> bool:
        """
        Atomically point the search alias to new_index and remove all previous indexes.
        Ensures zero-downtime reindexing.
        """
        target_alias = alias or OpenSearchConfigBuilder.get_index_alias()
        logger.info("Switching alias '%s' to point exclusively to '%s'...", target_alias, new_index)

        actions = []
        try:
            # Find all indexes currently attached to target_alias
            if self.client.indices.exists_alias(name=target_alias):
                current_aliases = self.client.indices.get_alias(name=target_alias)
                for existing_index in current_aliases.keys():
                    if existing_index != new_index:
                        actions.append({"remove": {"index": existing_index, "alias": target_alias}})

            actions.append({"add": {"index": new_index, "alias": target_alias}})

            body = {"actions": actions}
            self.client.indices.update_aliases(body=body)
            logger.info("Alias '%s' successfully pointed to '%s'", target_alias, new_index)
            return True
        except OpenSearchException as exc:
            logger.error("Failed to atomically swap alias '%s' to '%s': %s", target_alias, new_index, exc)
            raise

    def get_index_stats(self) -> Dict[str, Any]:
        """Query index statistics (document count, deleted count, size)."""
        try:
            stats = self.client.indices.stats(index=self.index_name)
            primaries = stats.get("indices", {}).get(self.index_name, {}).get("primaries", {})
            docs = primaries.get("docs", {})
            store = primaries.get("store", {})
            return {
                "index_name": self.index_name,
                "document_count": docs.get("count", 0),
                "deleted_count": docs.get("deleted", 0),
                "size_in_bytes": store.get("size_in_bytes", 0),
            }
        except OpenSearchException as exc:
            logger.warning("Could not retrieve stats for index '%s': %s", self.index_name, exc)
            return {
                "index_name": self.index_name,
                "document_count": 0,
                "deleted_count": 0,
                "size_in_bytes": 0,
                "error": str(exc),
            }
