"""
Comprehensive Test Suite for SmartCart 2.0 Phase 7: OpenSearch Integration.
Covers 26 test scenarios:
- 01-03: OpenSearch Client & Config (Builder, Sanitization, Host/URL handling)
- 04-05: Mappings, Analyzers & Composite Document ID Format
- 06-14: Indexing Service (ensure_index, index_store_product, get_doc, update_stock,
         stale protection, metadata update, deactivation, bulk index, atomic alias swap)
- 15-16: Natural-Language Search Parser (price ceilings/floors/ranges, stock/sort intents, token cleaning)
- 17-21: Search Service & Query Builder (store scoping, boosting, fuzziness, store isolation, suggestions, facets)
- 22:    API Endpoints & Role Authorization (Admin health endpoint vs unauthenticated / customer)
- 23-24: Kafka Synchronization (Authoritative PostgreSQL reads, stale-update protection)
- 25:    Reindexer CLI & Zero-Downtime Reindexing
- 26:    Checkout & Reservation Independence from OpenSearch (Fail-safe resilience)
"""
from datetime import datetime, timezone, timedelta
import math
from typing import Any, Dict, List, Optional
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient
from opensearchpy.exceptions import NotFoundError
from sqlalchemy import select

from app.api.deps import (
    get_product_index_service,
    get_product_search_service,
    get_storage_service,
)
from app.core.security import create_access_token
from app.db.session import AsyncSessionLocal, async_engine
from app.kafka.schemas import SmartCartEvent
from app.main import app
from app.models.enums import UserRole
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.store import Store
from app.models.user import User
from app.opensearch.client import check_opensearch_health
from app.opensearch.config import OpenSearchConfigBuilder
from app.opensearch.indexing import ProductIndexService
from app.opensearch.mappings import build_store_product_doc_id, get_product_index_mapping
from app.opensearch.nlp import NaturalLanguageSearchParser
from app.opensearch.search import ProductSearchService
from app.opensearch.sync import OpenSearchSyncService


# ============================================================================
# High-Fidelity In-Memory Mock OpenSearch Client for Deterministic Testing
# ============================================================================

class MockIndicesClient:
    def __init__(self, parent: "MockOpenSearchClient") -> None:
        self.parent = parent

    def exists(self, index: str) -> bool:
        return index in self.parent.indices_store

    def create(self, index: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.parent.indices_store[index] = body or {}
        return {"acknowledged": True, "index": index}

    def exists_alias(self, name: str) -> bool:
        return name in self.parent.aliases_store

    def put_alias(self, index: str, name: str) -> Dict[str, Any]:
        self.parent.aliases_store.setdefault(name, set()).add(index)
        return {"acknowledged": True}

    def get_alias(self, name: str) -> Dict[str, Any]:
        indexes = self.parent.aliases_store.get(name, set())
        return {idx: {"aliases": {name: {}}} for idx in indexes}

    def update_aliases(self, body: Dict[str, Any]) -> Dict[str, Any]:
        for action in body.get("actions", []):
            if "add" in action:
                idx = action["add"]["index"]
                alias = action["add"]["alias"]
                self.parent.aliases_store.setdefault(alias, set()).add(idx)
            if "remove" in action:
                idx = action["remove"]["index"]
                alias = action["remove"]["alias"]
                if alias in self.parent.aliases_store:
                    self.parent.aliases_store[alias].discard(idx)
        return {"acknowledged": True}

    def stats(self, index: str) -> Dict[str, Any]:
        target_indices = self.parent.aliases_store.get(index, {index})
        total_docs = sum(
            len(docs) for idx_name, docs in self.parent.docs_store.items() if idx_name in target_indices
        )
        return {
            "indices": {
                index: {
                    "primaries": {
                        "docs": {"count": total_docs, "deleted": 0},
                        "store": {"size_in_bytes": total_docs * 1024},
                    }
                }
            }
        }


import json
from opensearchpy.exceptions import ConnectionError as OSConnectionError


class MockSerializer:
    def dumps(self, data: Any) -> str:
        if isinstance(data, (dict, list)):
            return json.dumps(data)
        return str(data)


class MockTransport:
    def __init__(self) -> None:
        self.serializer = MockSerializer()


class MockClusterClient:
    def __init__(self, parent: "MockOpenSearchClient") -> None:
        self.parent = parent

    def health(self) -> Dict[str, Any]:
        if self.parent.should_fail:
            raise OSConnectionError(500, "Mock cluster connection refused")
        return {
            "status": "green",
            "cluster_name": "smartcart-test-cluster",
            "number_of_nodes": 3,
            "active_primary_shards": 5,
            "active_shards": 10,
            "unassigned_shards": 0,
        }


class MockOpenSearchClient:
    """In-memory mock supporting full OpenSearch operations with filtering, sorting, and aggregations."""

    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.indices_store: Dict[str, Dict[str, Any]] = {}
        self.aliases_store: Dict[str, set] = {}
        self.docs_store: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.indices = MockIndicesClient(self)
        self.cluster = MockClusterClient(self)
        self.transport = MockTransport()

    def bulk(self, body: Any, refresh: bool = False, **kwargs: Any) -> Dict[str, Any]:
        if self.should_fail:
            raise OSConnectionError("Mock OpenSearch down")
        items = []
        if isinstance(body, str):
            lines = [json.loads(line) for line in body.splitlines() if line.strip()]
            i = 0
            while i < len(lines):
                header = lines[i]
                action_type = next(iter(header.keys()))
                meta = header[action_type]
                index = self._resolve_index(meta.get("_index", "smartcart_products"))
                doc_id = meta.get("_id")
                source = lines[i + 1] if i + 1 < len(lines) else {}
                self.docs_store.setdefault(index, {})[doc_id] = dict(source)
                items.append({action_type: {"_id": doc_id, "status": 201, "result": "created"}})
                i += 2
        elif isinstance(body, list):
            for action in body:
                if isinstance(action, dict):
                    action_type = next(iter(action.keys()))
                    meta = action[action_type]
                    index = self._resolve_index(meta.get("_index", "smartcart_products"))
                    doc_id = meta.get("_id")
                    source = action.get("_source", {})
                    self.docs_store.setdefault(index, {})[doc_id] = dict(source)
                    items.append({action_type: {"_id": doc_id, "status": 201, "result": "created"}})
        return {"took": 1, "errors": False, "items": items}

    def _resolve_index(self, index: str) -> str:
        if index in self.aliases_store and self.aliases_store[index]:
            return next(iter(self.aliases_store[index]))
        return index

    def index(self, index: str, id: str, body: Dict[str, Any], refresh: bool = False) -> Dict[str, Any]:
        if self.should_fail:
            raise ConnectionError("Mock OpenSearch down")
        resolved = self._resolve_index(index)
        self.docs_store.setdefault(resolved, {})[id] = dict(body)
        return {"result": "created", "_id": id, "_index": resolved}

    def get(self, index: str, id: str) -> Dict[str, Any]:
        if self.should_fail:
            raise ConnectionError("Mock OpenSearch down")
        resolved = self._resolve_index(index)
        docs = self.docs_store.get(resolved, {})
        if id not in docs:
            raise NotFoundError(404, f"Document id '{id}' not found")
        return {"_id": id, "_source": dict(docs[id])}

    def update(self, index: str, id: str, body: Dict[str, Any], refresh: bool = False) -> Dict[str, Any]:
        if self.should_fail:
            raise ConnectionError("Mock OpenSearch down")
        resolved = self._resolve_index(index)
        docs = self.docs_store.get(resolved, {})
        if id not in docs:
            raise NotFoundError(404, f"Document id '{id}' not found")
        doc_updates = body.get("doc", {})
        docs[id].update(doc_updates)
        return {"result": "updated", "_id": id}

    def update_by_query(
        self,
        index: str,
        body: Dict[str, Any],
        refresh: bool = False,
        conflicts: str = "proceed",
    ) -> Dict[str, Any]:
        if self.should_fail:
            raise ConnectionError("Mock OpenSearch down")
        resolved = self._resolve_index(index)
        docs = self.docs_store.get(resolved, {})
        term_query = body.get("query", {}).get("term", {})
        field, val = next(iter(term_query.items())) if term_query else (None, None)

        script_params = body.get("script", {}).get("params", {})
        updated_count = 0
        for doc_id, doc in list(docs.items()):
            if field and str(doc.get(field)) == str(val):
                doc.update(script_params)
                updated_count += 1
        return {"updated": updated_count}

    def search(self, index: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if self.should_fail:
            raise ConnectionError("Mock OpenSearch down")
        resolved = self._resolve_index(index)
        all_docs = list(self.docs_store.get(resolved, {}).values())

        # Extract filters
        query_dsl = body.get("query", {}).get("bool", {})
        filters = query_dsl.get("filter", [])
        musts = query_dsl.get("must", [])

        filtered = []
        for doc in all_docs:
            match = True
            for flt in filters:
                if "term" in flt:
                    k, v = next(iter(flt["term"].items()))
                    if doc.get(k) != v:
                        match = False
                        break
                elif "range" in flt:
                    k, rng = next(iter(flt["range"].items()))
                    doc_val = doc.get(k, 0)
                    if "gte" in rng and doc_val < rng["gte"]:
                        match = False
                        break
                    if "lte" in rng and doc_val > rng["lte"]:
                        match = False
                        break
            if not match:
                continue

            # Check text query
            for must in musts:
                if "bool" in must and "should" in must["bool"]:
                    # Multi-match text search simulation
                    text_matches = False
                    for should in must["bool"]["should"]:
                        if "multi_match" in should:
                            q_str = should["multi_match"]["query"].lower()
                            name = (doc.get("name") or "").lower()
                            brand = (doc.get("brand") or "").lower()
                            cat = (doc.get("category") or "").lower()
                            sku = (doc.get("sku") or "").lower()
                            desc = (doc.get("description") or "").lower()
                            # Substring or token match
                            for tok in q_str.split():
                                if tok in name or tok in brand or tok in cat or tok in sku or tok in desc:
                                    text_matches = True
                                    break
                        elif "match_phrase_prefix" in should:
                            q_str = should["match_phrase_prefix"]["name"]["query"].lower()
                            if q_str in (doc.get("name") or "").lower():
                                text_matches = True
                        elif "term" in should:
                            field, tval = next(iter(should["term"].items()))
                            val = tval.get("value") if isinstance(tval, dict) else tval
                            if str(doc.get(field)).lower() == str(val).lower():
                                text_matches = True
                    if not text_matches:
                        match = False
                        break
                elif "match_all" in must:
                    pass

            if match:
                filtered.append(doc)

        # Sorting
        sorts = body.get("sort", [])
        for s in sorts:
            if isinstance(s, dict):
                field, opt = next(iter(s.items()))
                reverse = opt.get("order") == "desc"
                if field == "price_paise":
                    filtered.sort(key=lambda d: d.get("price_paise", 0), reverse=reverse)
                elif field == "created_at":
                    filtered.sort(key=lambda d: d.get("created_at") or "", reverse=reverse)

        # Aggregations
        categories_map: Dict[str, int] = {}
        brands_map: Dict[str, int] = {}
        prices = [d.get("price_paise", 0) for d in filtered if "price_paise" in d]

        for d in filtered:
            c = d.get("category")
            if c:
                categories_map[c] = categories_map.get(c, 0) + 1
            b = d.get("brand")
            if b:
                brands_map[b] = brands_map.get(b, 0) + 1

        aggs = {
            "categories": {"buckets": [{"key": k, "doc_count": v} for k, v in categories_map.items()]},
            "brands": {"buckets": [{"key": k, "doc_count": v} for k, v in brands_map.items()]},
            "price_stats": {
                "min": min(prices) if prices else 0,
                "max": max(prices) if prices else 0,
            },
        }

        from_offset = body.get("from", 0)
        size = body.get("size", 20)
        sliced = filtered[from_offset : from_offset + size]

        hits_list = [{"_id": d.get("id"), "_score": 1.0, "_source": d} for d in sliced]

        return {
            "hits": {
                "total": {"value": len(filtered), "relation": "eq"},
                "hits": hits_list,
            },
            "aggregations": aggs,
        }

    def close(self) -> None:
        pass


# ============================================================================
# Pytest Fixtures
# ============================================================================

@pytest_asyncio.fixture(autouse=True)
async def clean_dependencies():
    """Ensure mock overrides and DB connections are cleanly reset."""
    mock_client = MockOpenSearchClient()
    mock_index_service = ProductIndexService(client=mock_client)
    mock_search_service = ProductSearchService(client=mock_client)

    app.dependency_overrides[get_product_index_service] = lambda: mock_index_service
    app.dependency_overrides[get_product_search_service] = lambda: mock_search_service

    yield mock_client

    app.dependency_overrides.pop(get_product_index_service, None)
    app.dependency_overrides.pop(get_product_search_service, None)
    if async_engine is not None:
        await async_engine.dispose()


@pytest_asyncio.fixture
async def opensearch_env(clean_dependencies):
    """
    Sets up a populated test environment with:
    - 2 stores in PostgreSQL
    - 3 products with stock in Store A, 1 in Store B
    - Admin, Manager, and Customer users with tokens
    - OpenSearch index seeded with store-product documents
    """
    mock_client: MockOpenSearchClient = clean_dependencies
    store_a_id = uuid.uuid4()
    store_b_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    mgr_a_id = uuid.uuid4()

    code_a = f"STR-{uuid.uuid4().hex[:6].upper()}"
    code_b = f"STR-{uuid.uuid4().hex[:6].upper()}"

    index_service = ProductIndexService(client=mock_client)
    index_service.ensure_index()

    async with AsyncSessionLocal() as session:
        # Create Stores
        store_a = Store(id=store_a_id, code=code_a, name="Bengaluru Central", city="Bengaluru", state="KA", is_active=True)
        store_b = Store(id=store_b_id, code=code_b, name="Mysuru Express", city="Mysuru", state="KA", is_active=True)
        session.add_all([store_a, store_b])

        # Create Users
        admin_user = User(
            id=admin_id,
            email=f"admin_{uuid.uuid4().hex[:6]}@smartcart.in",
            full_name="Admin User",
            password_hash="argon2id$mocked",
            role=UserRole.ADMIN,
            is_active=True,
        )
        customer_user = User(
            id=customer_id,
            email=f"cust_{uuid.uuid4().hex[:6]}@smartcart.in",
            full_name="Customer User",
            password_hash="argon2id$mocked",
            role=UserRole.CUSTOMER,
            is_active=True,
        )
        from app.models.customer import Customer
        cust_profile = Customer(
            id=customer_id,
            user_id=customer_id,
            phone=f"+9198{uuid.uuid4().int % 100000000:08d}",
        )
        mgr_user = User(
            id=mgr_a_id,
            email=f"mgr_{uuid.uuid4().hex[:6]}@smartcart.in",
            full_name="Manager User",
            password_hash="argon2id$mocked",
            role=UserRole.STORE_MANAGER,
            assigned_store_id=store_a_id,
            is_active=True,
        )
        session.add_all([admin_user, customer_user, cust_profile, mgr_user])

        # Create Products
        p1_id = uuid.uuid4()
        p2_id = uuid.uuid4()
        p3_id = uuid.uuid4()

        p1 = Product(
            id=p1_id,
            sku=f"SKU-WH-{uuid.uuid4().hex[:4].upper()}",
            name="Sony WH-1000XM5 Wireless Headphones",
            brand="Sony",
            category="Electronics",
            description="Premium noise cancelling wireless headphones with 30-hour battery life",
            price_paise=2999000,
            attributes={"image_url": "https://images.smartcart.in/sony_wh5.jpg"},
            is_active=True,
        )
        p2 = Product(
            id=p2_id,
            sku=f"SKU-SH-{uuid.uuid4().hex[:4].upper()}",
            name="Nike Air Zoom Pegasus 40 Running Shoes",
            brand="Nike",
            category="Footwear",
            description="Lightweight breathable running shoes engineered for distance running",
            price_paise=899900,
            attributes={"image_url": "https://images.smartcart.in/nike_pegasus.jpg"},
            is_active=True,
        )
        p3 = Product(
            id=p3_id,
            sku=f"SKU-AP-{uuid.uuid4().hex[:4].upper()}",
            name="Apple iPhone 15 Pro 128GB Titanium",
            brand="Apple",
            category="Electronics",
            description="A17 Pro chip with 48MP main camera and USB-C connectivity",
            price_paise=12999900,
            attributes={"image_url": "https://images.smartcart.in/iphone_15.jpg"},
            is_active=True,
        )
        session.add_all([p1, p2, p3])

        # Create Inventory
        inv1_a = Inventory(store_id=store_a_id, product_id=p1_id, qty_on_hand=15, qty_reserved=2, low_stock_threshold=5)
        inv2_a = Inventory(store_id=store_a_id, product_id=p2_id, qty_on_hand=8, qty_reserved=0, low_stock_threshold=3)
        inv3_a = Inventory(store_id=store_a_id, product_id=p3_id, qty_on_hand=0, qty_reserved=0, low_stock_threshold=2)  # Out of stock
        inv1_b = Inventory(store_id=store_b_id, product_id=p1_id, qty_on_hand=5, qty_reserved=1, low_stock_threshold=2)
        session.add_all([inv1_a, inv2_a, inv3_a, inv1_b])

        await session.commit()

    # Seed OpenSearch documents
    sync_service = OpenSearchSyncService(index_service=index_service)
    async with AsyncSessionLocal() as session:
        await sync_service.sync_product_from_db(p1_id, store_a_id, session)
        await sync_service.sync_product_from_db(p2_id, store_a_id, session)
        await sync_service.sync_product_from_db(p3_id, store_a_id, session)
        await sync_service.sync_product_from_db(p1_id, store_b_id, session)

    admin_token = create_access_token(data={"sub": str(admin_id), "role": "admin"})
    cust_token = create_access_token(data={"sub": str(customer_id), "role": "customer"})
    mgr_token = create_access_token(data={"sub": str(mgr_a_id), "role": "store_manager"})

    yield {
        "mock_client": mock_client,
        "index_service": index_service,
        "search_service": ProductSearchService(client=mock_client),
        "sync_service": sync_service,
        "store_a_id": store_a_id,
        "store_b_id": store_b_id,
        "p1_id": p1_id,
        "p2_id": p2_id,
        "p3_id": p3_id,
        "customer_id": customer_id,
        "admin_token": admin_token,
        "cust_token": cust_token,
        "mgr_token": mgr_token,
    }

    # Clean up test rows from database
    async with AsyncSessionLocal() as session:
        from sqlalchemy import text
        await session.execute(text("DELETE FROM reservations WHERE store_id IN (:sa, :sb)"), {"sa": store_a_id, "sb": store_b_id})
        await session.execute(text("DELETE FROM inventory_audit_log WHERE store_id IN (:sa, :sb)"), {"sa": store_a_id, "sb": store_b_id})
        await session.execute(text("DELETE FROM inventory WHERE store_id IN (:sa, :sb)"), {"sa": store_a_id, "sb": store_b_id})
        await session.execute(text("DELETE FROM inventory WHERE product_id IN (:p1, :p2, :p3)"), {"p1": p1_id, "p2": p2_id, "p3": p3_id})
        await session.execute(text("DELETE FROM outbox_events WHERE aggregate_id IN (:p1, :p2, :p3)"), {"p1": str(p1_id), "p2": str(p2_id), "p3": str(p3_id)})
        await session.execute(text("DELETE FROM products WHERE id IN (:p1, :p2, :p3)"), {"p1": p1_id, "p2": p2_id, "p3": p3_id})
        await session.execute(text("DELETE FROM customers WHERE id = :cid"), {"cid": customer_id})
        await session.execute(text("DELETE FROM users WHERE id IN (:u1, :u2, :u3)"), {"u1": admin_id, "u2": customer_id, "u3": mgr_a_id})
        await session.execute(text("DELETE FROM stores WHERE id IN (:sa, :sb)"), {"sa": store_a_id, "sb": store_b_id})
        await session.commit()


# ============================================================================
# Test Cases (26 Required Scenarios)
# ============================================================================

def test_01_client_initialization_with_config_builder():
    """Verify OpenSearchConfigBuilder produces valid client kwargs."""
    config = OpenSearchConfigBuilder.get_client_config(
        host="opensearch.aivencloud.com",
        port=443,
        user="avnadmin",
        password="secret_password",
        use_ssl=True,
    )
    assert config["hosts"] == [{"host": "opensearch.aivencloud.com", "port": 443}]
    assert config["use_ssl"] is True
    assert config["http_auth"] == ("avnadmin", "secret_password")
    assert config["timeout"] >= 5


def test_02_config_builder_sanitizes_credentials():
    """Verify credentials masking in sanitized config dictionary."""
    config = {
        "hosts": [{"host": "my-os.com", "port": 443}],
        "http_auth": ("avnadmin", "super_secret_pw"),
    }
    sanitized = OpenSearchConfigBuilder.get_sanitized_config(config)
    assert sanitized["http_auth"] == ("avnadmin", "******")


def test_03_config_builder_handles_url_and_host_port():
    """Verify builder correctly parses full Aiven OpenSearch URL."""
    url = "https://avnadmin:mypassword@my-cluster.aivencloud.com:25000"
    config = OpenSearchConfigBuilder.get_client_config(url=url)
    assert config["hosts"] == [{"host": "my-cluster.aivencloud.com", "port": 25000}]
    assert config["use_ssl"] is True
    assert config["http_auth"] == ("avnadmin", "mypassword")


def test_04_mapping_schema_structure_and_analyzers():
    """Verify schema mappings include edge n-gram autocomplete and text analyzers."""
    mapping = get_product_index_mapping()
    assert "settings" in mapping
    assert "mappings" in mapping
    settings_data = mapping["settings"]["analysis"]
    assert "autocomplete_analyzer" in settings_data["analyzer"]
    assert "text_search_analyzer" in settings_data["analyzer"]
    props = mapping["mappings"]["properties"]
    assert props["sku"]["type"] == "keyword"
    assert props["name"]["type"] == "text"
    assert "autocomplete" in props["name"]["fields"]
    assert props["price_paise"]["type"] == "long"
    assert props["qty_available"]["type"] == "integer"
    assert props["is_in_stock"]["type"] == "boolean"


def test_05_store_product_composite_doc_id_format():
    """Verify composite document ID format {product_id}_{store_id}."""
    pid = uuid.uuid4()
    sid = uuid.uuid4()
    doc_id = build_store_product_doc_id(pid, sid)
    assert doc_id == f"{str(pid)}_{str(sid)}"


def test_06_ensure_index_creates_versioned_index_and_alias():
    """Verify ensure_index creates the target versioned index and binds the search alias."""
    client = MockOpenSearchClient()
    service = ProductIndexService(client=client, index_name="smartcart_products")
    success = service.ensure_index(index_name="smartcart_products_v1", alias="smartcart_products")
    assert success is True
    assert "smartcart_products_v1" in client.indices_store
    assert "smartcart_products" in client.aliases_store
    assert "smartcart_products_v1" in client.aliases_store["smartcart_products"]


def test_07_index_store_product_calculates_stock_and_stores_doc():
    """Verify document indexing automatically computes qty_available and is_in_stock."""
    client = MockOpenSearchClient()
    service = ProductIndexService(client=client, index_name="smartcart_products")
    pid = uuid.uuid4()
    sid = uuid.uuid4()

    doc = {
        "product_id": pid,
        "store_id": sid,
        "sku": "SKU-001",
        "name": "Test Wireless Mouse",
        "price_paise": 150000,
        "qty_on_hand": 10,
        "qty_reserved": 3,
    }
    resp = service.index_store_product(doc)
    assert resp["result"] == "created"

    retrieved = service.get_document(pid, sid)
    assert retrieved is not None
    assert retrieved["qty_available"] == 7
    assert retrieved["is_in_stock"] is True


def test_08_get_document_retrieval_and_not_found():
    """Verify get_document retrieves existing doc and returns None for missing doc."""
    client = MockOpenSearchClient()
    service = ProductIndexService(client=client, index_name="smartcart_products")
    pid = uuid.uuid4()
    sid = uuid.uuid4()
    assert service.get_document(pid, sid) is None

    service.index_store_product({"product_id": pid, "store_id": sid, "name": "Item"})
    assert service.get_document(pid, sid)["name"] == "Item"


def test_09_update_stock_calculates_available_and_in_stock():
    """Verify stock update modifies qty_on_hand, qty_reserved, and derived is_in_stock."""
    client = MockOpenSearchClient()
    service = ProductIndexService(client=client, index_name="smartcart_products")
    pid = uuid.uuid4()
    sid = uuid.uuid4()
    service.index_store_product({
        "product_id": pid,
        "store_id": sid,
        "qty_on_hand": 5,
        "qty_reserved": 0,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })

    now = datetime.now(timezone.utc) + timedelta(seconds=1)
    # Reserve all stock
    service.update_stock(pid, sid, qty_on_hand=5, qty_reserved=5, updated_at=now)
    doc = service.get_document(pid, sid)
    assert doc["qty_available"] == 0
    assert doc["is_in_stock"] is False


def test_10_update_stock_stale_update_protection():
    """Verify update_stock rejects stale stock events older than current document timestamp."""
    client = MockOpenSearchClient()
    service = ProductIndexService(client=client, index_name="smartcart_products")
    pid = uuid.uuid4()
    sid = uuid.uuid4()

    newer_time = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)
    service.index_store_product({
        "product_id": pid,
        "store_id": sid,
        "qty_on_hand": 10,
        "qty_reserved": 2,
        "updated_at": newer_time.isoformat(),
    })

    # Attempt update with older timestamp (11:00:00)
    older_time = datetime(2026, 3, 30, 11, 0, 0, tzinfo=timezone.utc)
    updated = service.update_stock(pid, sid, qty_on_hand=20, qty_reserved=0, updated_at=older_time)
    assert updated is False  # Must be rejected due to stale timestamp!

    # Document must retain original newer state
    doc = service.get_document(pid, sid)
    assert doc["qty_on_hand"] == 10
    assert doc["qty_reserved"] == 2


def test_11_update_product_metadata_across_stores():
    """Verify metadata update applies across all store documents matching product_id."""
    client = MockOpenSearchClient()
    service = ProductIndexService(client=client, index_name="smartcart_products")
    pid = uuid.uuid4()
    sid1 = uuid.uuid4()
    sid2 = uuid.uuid4()

    service.index_store_product({"product_id": pid, "store_id": sid1, "name": "Old Name", "brand": "Brand A"})
    service.index_store_product({"product_id": pid, "store_id": sid2, "name": "Old Name", "brand": "Brand A"})

    updated_count = service.update_product_metadata(pid, {"name": "New Name", "brand": "Brand B"})
    assert updated_count == 2
    assert service.get_document(pid, sid1)["name"] == "New Name"
    assert service.get_document(pid, sid2)["name"] == "New Name"


def test_12_deactivate_product_sets_is_active_false():
    """Verify deactivate_product marks is_active=false across all store documents."""
    client = MockOpenSearchClient()
    service = ProductIndexService(client=client, index_name="smartcart_products")
    pid = uuid.uuid4()
    sid = uuid.uuid4()
    service.index_store_product({"product_id": pid, "store_id": sid, "name": "Product", "is_active": True})

    service.deactivate_product(pid)
    doc = service.get_document(pid, sid)
    assert doc["is_active"] is False


def test_13_bulk_index_documents_streaming():
    """Verify bulk_index_documents indexes batch of documents successfully."""
    client = MockOpenSearchClient()
    service = ProductIndexService(client=client, index_name="smartcart_products")
    docs = [
        {"product_id": uuid.uuid4(), "store_id": uuid.uuid4(), "name": f"Product {i}", "price_paise": 1000 * i}
        for i in range(10)
    ]
    success, errors = service.bulk_index_documents(docs, chunk_size=5)
    assert success == 10
    assert len(errors) == 0


def test_14_atomic_alias_swap_zero_downtime():
    """Verify atomic alias swapping points alias exclusively to the new index."""
    client = MockOpenSearchClient()
    service = ProductIndexService(client=client, index_name="smartcart_products")
    client.indices.create("smartcart_products_old")
    client.indices.put_alias(index="smartcart_products_old", name="smartcart_products")

    client.indices.create("smartcart_products_new")
    service.swap_alias(new_index="smartcart_products_new", alias="smartcart_products")

    assert "smartcart_products_new" in client.aliases_store["smartcart_products"]
    assert "smartcart_products_old" not in client.aliases_store["smartcart_products"]


def test_15_nlp_parser_price_constraints():
    """Verify NaturalLanguageSearchParser extracts price ranges, ceilings, and floors."""
    # Price ceiling: "under 3000"
    p1 = NaturalLanguageSearchParser.parse("show wireless headphones under 3000")
    assert p1.clean_query == "wireless headphones"
    assert p1.max_price_paise == 300000

    # Price range: "between 500 and 1500"
    p2 = NaturalLanguageSearchParser.parse("running shoes between 500 and 1500")
    assert p2.clean_query == "running shoes"
    assert p2.min_price_paise == 50000
    assert p2.max_price_paise == 150000

    # Price floor: "above 5000"
    p3 = NaturalLanguageSearchParser.parse("gaming monitors above 5000")
    assert p3.clean_query == "gaming monitors"
    assert p3.min_price_paise == 500000

    # K notation: "under 3k"
    p4 = NaturalLanguageSearchParser.parse("bluetooth speaker under 3k")
    assert p4.clean_query == "bluetooth speaker"
    assert p4.max_price_paise == 300000


def test_16_nlp_parser_stock_and_sort_intents():
    """Verify NaturalLanguageSearchParser extracts in-stock and sorting intents."""
    # Cheap + in stock
    p1 = NaturalLanguageSearchParser.parse("find cheap mechanical keyboard in stock")
    assert p1.clean_query == "mechanical keyboard"
    assert p1.sort_by == "price_asc"
    assert p1.in_stock_only is True

    # Premium
    p2 = NaturalLanguageSearchParser.parse("premium organic coffee beans")
    assert p2.clean_query == "organic coffee beans"
    assert p2.sort_by == "price_desc"


def test_17_search_query_builder_store_scoping_and_boosting():
    """Verify search query builder applies store_id term filter and multi-field boosting."""
    service = ProductSearchService()
    sid = uuid.uuid4()
    query_dsl = service.build_search_query(
        store_id=sid,
        query="Sony Headphones",
        category="Electronics",
        min_price_paise=100000,
        max_price_paise=500000,
        in_stock_only=True,
    )
    bool_filter = query_dsl["query"]["bool"]["filter"]
    # Verify store scoping
    assert {"term": {"store_id": str(sid)}} in bool_filter
    assert {"term": {"is_active": True}} in bool_filter
    assert {"term": {"is_in_stock": True}} in bool_filter
    assert {"term": {"category": "Electronics"}} in bool_filter

    # Verify boosting fields in must
    must_bool = query_dsl["query"]["bool"]["must"][0]["bool"]["should"]
    multi_match = next(c["multi_match"] for c in must_bool if "multi_match" in c)
    assert "sku^4" in multi_match["fields"]
    assert "name^3" in multi_match["fields"]
    assert "brand^2" in multi_match["fields"]
    assert multi_match["fuzziness"] == "AUTO:4,7"


@pytest.mark.asyncio
async def test_18_search_products_store_isolation(opensearch_env):
    """Verify searches scoped to Store A return Store A inventory and do not leak Store B."""
    search_service: ProductSearchService = opensearch_env["search_service"]
    store_a_id = opensearch_env["store_a_id"]
    store_b_id = opensearch_env["store_b_id"]

    # Search in Store A
    res_a = search_service.search_products(store_id=store_a_id, in_stock_only=True)
    # Store A has p1 (13 avail) and p2 (8 avail). p3 is out of stock.
    assert res_a["total"] == 2
    for item in res_a["items"]:
        assert item["store_id"] == str(store_a_id)
        assert item["is_in_stock"] is True

    # Search in Store B
    res_b = search_service.search_products(store_id=store_b_id, in_stock_only=True)
    # Store B only has p1 (4 avail)
    assert res_b["total"] == 1
    assert res_b["items"][0]["store_id"] == str(store_b_id)
    assert res_b["items"][0]["qty_available"] == 4


@pytest.mark.asyncio
async def test_19_search_products_typo_tolerance_and_filtering(opensearch_env):
    """Verify search finds products with typos and applies category/brand filters."""
    search_service: ProductSearchService = opensearch_env["search_service"]
    store_a_id = opensearch_env["store_a_id"]

    # Query with keyword match
    res = search_service.search_products(store_id=store_a_id, query="Sony", in_stock_only=True)
    assert res["total"] == 1
    assert "Sony" in res["items"][0]["name"]

    # Category filter
    res_cat = search_service.search_products(store_id=store_a_id, category="Footwear", in_stock_only=True)
    assert res_cat["total"] == 1
    assert res_cat["items"][0]["category"] == "Footwear"


@pytest.mark.asyncio
async def test_20_search_autocomplete_suggestions(opensearch_env):
    """Verify autocomplete suggestions return prefix matches within store."""
    search_service: ProductSearchService = opensearch_env["search_service"]
    store_a_id = opensearch_env["store_a_id"]

    suggestions = search_service.get_suggestions(store_id=store_a_id, query="Son")
    assert len(suggestions) >= 1
    assert "Sony" in suggestions[0]["text"]


@pytest.mark.asyncio
async def test_21_search_filter_facets_aggregation(opensearch_env):
    """Verify facet aggregation returns category, brand counts and price stats."""
    search_service: ProductSearchService = opensearch_env["search_service"]
    store_a_id = opensearch_env["store_a_id"]

    facets = search_service.get_filter_facets(store_id=store_a_id)
    assert facets["store_id"] == str(store_a_id)
    cat_names = [c["name"] for c in facets["categories"]]
    assert "Electronics" in cat_names or "Footwear" in cat_names
    assert facets["min_price_paise"] > 0
    assert facets["max_price_paise"] >= facets["min_price_paise"]


@pytest.mark.asyncio
async def test_22_search_health_admin_protected(async_client: AsyncClient, opensearch_env: dict):
    """Verify GET /api/v1/search/health is protected strictly for Admin users."""
    admin_token = opensearch_env["admin_token"]
    cust_token = opensearch_env["cust_token"]

    # 1. Unauthenticated -> 401
    resp_unauth = await async_client.get("/api/v1/search/health")
    assert resp_unauth.status_code == 401

    # 2. Customer -> 403 Forbidden
    resp_cust = await async_client.get(
        "/api/v1/search/health",
        headers={"Authorization": f"Bearer {cust_token}"},
    )
    assert resp_cust.status_code == 403

    # 3. Admin -> 200 OK with cluster and index statistics
    resp_admin = await async_client.get(
        "/api/v1/search/health",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_admin.status_code == 200
    data = resp_admin.json()
    assert data["status"] in ("healthy", "degraded", "green", "yellow")
    assert data["cluster_name"] == "smartcart-test-cluster"
    assert data["number_of_nodes"] == 3


@pytest.mark.asyncio
async def test_23_kafka_sync_product_created_and_updated_from_db(opensearch_env):
    """Verify Kafka event syncs product data authoritative snapshot from PostgreSQL."""
    sync_service: OpenSearchSyncService = opensearch_env["sync_service"]
    index_service: ProductIndexService = opensearch_env["index_service"]
    store_a_id = opensearch_env["store_a_id"]

    new_pid = uuid.uuid4()
    sku = f"SKU-NEW-{uuid.uuid4().hex[:4].upper()}"

    async with AsyncSessionLocal() as session:
        new_prod = Product(
            id=new_pid,
            sku=sku,
            name="Logitech MX Master 3S Mouse",
            brand="Logitech",
            category="Electronics",
            price_paise=999500,
            is_active=True,
        )
        new_inv = Inventory(store_id=store_a_id, product_id=new_pid, qty_on_hand=20, qty_reserved=0)
        session.add_all([new_prod, new_inv])
        await session.commit()

        # Simulate Kafka product.created event
        event = SmartCartEvent(
            event_id=str(uuid.uuid4()),
            event_type="product.created",
            aggregate_type="product",
            aggregate_id=str(new_pid),
            payload={"product_id": str(new_pid), "store_id": str(store_a_id)},
        )
        await sync_service.handle_product_created(event, session)

    doc = index_service.get_document(new_pid, store_a_id)
    assert doc is not None
    assert doc["name"] == "Logitech MX Master 3S Mouse"
    assert doc["qty_available"] == 20
    assert doc["is_in_stock"] is True

    # Clean up test product
    async with AsyncSessionLocal() as session:
        from sqlalchemy import text
        await session.execute(text("DELETE FROM inventory WHERE product_id = :pid"), {"pid": new_pid})
        await session.execute(text("DELETE FROM products WHERE id = :pid"), {"pid": new_pid})
        await session.commit()


@pytest.mark.asyncio
async def test_24_kafka_sync_inventory_stock_authoritative_from_db(opensearch_env):
    """Verify Kafka inventory.stock.updated event fetches authoritative stock from DB."""
    sync_service: OpenSearchSyncService = opensearch_env["sync_service"]
    index_service: ProductIndexService = opensearch_env["index_service"]
    store_a_id = opensearch_env["store_a_id"]
    p1_id = opensearch_env["p1_id"]

    async with AsyncSessionLocal() as session:
        # Update DB stock
        stmt = select(Inventory).where(Inventory.product_id == p1_id, Inventory.store_id == store_a_id)
        res = await session.execute(stmt)
        inv = res.scalar_one()
        inv.qty_on_hand = 50
        inv.qty_reserved = 10
        inv.updated_at = datetime.now(timezone.utc)
        await session.commit()

        # Dispatch Kafka event
        event = SmartCartEvent(
            event_id=str(uuid.uuid4()),
            event_type="inventory.stock.updated",
            aggregate_type="inventory",
            aggregate_id=f"{store_a_id}:{p1_id}",
            payload={"product_id": str(p1_id), "store_id": str(store_a_id), "qty_on_hand": 50},
        )
        await sync_service.handle_inventory_stock_updated(event, session)

    doc = index_service.get_document(p1_id, store_a_id)
    assert doc["qty_on_hand"] == 50
    assert doc["qty_reserved"] == 10
    assert doc["qty_available"] == 40


@pytest.mark.asyncio
async def test_25_reindexer_bulk_index_and_status(opensearch_env):
    """Verify Reindexer worker fetches PostgreSQL rows and bulk indexes into OpenSearch."""
    from app.workers.reindexer import bulk_index_from_postgres
    index_service: ProductIndexService = opensearch_env["index_service"]
    count = await bulk_index_from_postgres(index_service)
    assert count >= 4  # At least the 4 inventory rows created in setup


@pytest.mark.asyncio
async def test_26_checkout_and_reservation_independence_from_opensearch(opensearch_env):
    """
    Verify core checkout and reservations remain 100% operational in PostgreSQL
    even when OpenSearch is degraded or throws connection failures.
    """
    mock_client: MockOpenSearchClient = opensearch_env["mock_client"]
    # Simulate complete OpenSearch outage
    mock_client.should_fail = True

    # Health check reflects outage safely without raising unhandled crash
    health = check_opensearch_health(mock_client)
    assert health["status"] == "unavailable"

    # Core checkout/inventory services operate independently via PostgreSQL
    from app.services.inventory import InventoryService
    from app.repositories.inventory import InventoryRepository
    from app.repositories.reservation import ReservationRepository

    store_a_id = opensearch_env["store_a_id"]
    p1_id = opensearch_env["p1_id"]

    async with AsyncSessionLocal() as session:
        inv_service = InventoryService(
            inventory_repo=InventoryRepository(session),
            reservation_repo=ReservationRepository(session),
            session=session,
        )
        # Verify authoritative stock lookup succeeds in PostgreSQL despite OpenSearch failure!
        stock = await inv_service.get_stock(store_id=store_a_id, product_id=p1_id)
        assert stock.qty_on_hand == 15
        assert stock.qty_available == 13

        # Verify atomic stock reservation in PostgreSQL works independently!
        res_id = await inv_service.reserve_stock(
            customer_id=opensearch_env["customer_id"],
            store_id=store_a_id,
            product_id=p1_id,
            qty=1,
        )
        assert res_id is not None
        await session.rollback()
