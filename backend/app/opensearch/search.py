"""
Product search service for SmartCart 2.0 OpenSearch.
Executes store-aware, typo-tolerant, multi-field boosted product discovery queries,
autocomplete prefix suggestions, dynamic facet aggregations, and pagination.
"""
import logging
import math
from typing import Any, Dict, List, Optional
from uuid import UUID

from opensearchpy import OpenSearch, OpenSearchException

from app.opensearch.client import get_opensearch_client
from app.opensearch.config import OpenSearchConfigBuilder
from app.opensearch.nlp import NaturalLanguageSearchParser

logger = logging.getLogger("smartcart.opensearch.search")


class ProductSearchService:
    """Service providing store-scoped product discovery and query execution against OpenSearch."""

    def __init__(
        self,
        client: Optional[OpenSearch] = None,
        index_name: Optional[str] = None,
    ) -> None:
        self.client: OpenSearch = client or get_opensearch_client()
        self.index_name: str = index_name or OpenSearchConfigBuilder.get_index_alias()

    def build_search_query(
        self,
        store_id: UUID,
        query: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        min_price_paise: Optional[int] = None,
        max_price_paise: Optional[int] = None,
        in_stock_only: bool = True,
        sort_by: str = "relevance",
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """
        Construct OpenSearch search query DSL with:
        - Strict store scoping (store_id)
        - Active catalog filtering (is_active=true)
        - Optional stock availability filter (is_in_stock=true)
        - Typo-tolerant multi-field search with relevance boosting
        - Exact term filters (category, brand, price range)
        - Dynamic facet aggregations
        """
        must_clauses: List[Dict[str, Any]] = []
        filter_clauses: List[Dict[str, Any]] = [
            {"term": {"store_id": str(store_id)}},
            {"term": {"is_active": True}},
        ]

        if in_stock_only:
            filter_clauses.append({"term": {"is_in_stock": True}})

        if category and category.strip():
            filter_clauses.append({"term": {"category": category.strip()}})

        if brand and brand.strip():
            filter_clauses.append({"term": {"brand": brand.strip()}})

        if min_price_paise is not None or max_price_paise is not None:
            range_filter: Dict[str, Any] = {}
            if min_price_paise is not None:
                range_filter["gte"] = int(min_price_paise)
            if max_price_paise is not None:
                range_filter["lte"] = int(max_price_paise)
            filter_clauses.append({"range": {"price_paise": range_filter}})

        # Text matching
        if query and query.strip():
            clean_q = query.strip()
            must_clauses.append({
                "bool": {
                    "should": [
                        # 1. Exact SKU / ID match
                        {"term": {"sku": {"value": clean_q, "boost": 6.0}}},
                        # 2. Multi-match with boosting and controlled fuzziness
                        {
                            "multi_match": {
                                "query": clean_q,
                                "fields": [
                                    "sku^4",
                                    "name^3",
                                    "brand^2",
                                    "category^2",
                                    "description^1",
                                ],
                                "type": "best_fields",
                                "fuzziness": "AUTO:4,7",
                                "prefix_length": 2,
                                "max_expansions": 50,
                            }
                        },
                        # 3. Match phrase prefix on name for partial words
                        {
                            "match_phrase_prefix": {
                                "name": {
                                    "query": clean_q,
                                    "boost": 2.5,
                                }
                            }
                        },
                    ],
                    "minimum_should_match": 1,
                }
            })
        else:
            # Match all active store products if query is empty
            must_clauses.append({"match_all": {}})

        # Sorting
        sort_clauses: List[Dict[str, Any]] = []
        normalized_sort = (sort_by or "relevance").lower()
        if normalized_sort == "price_asc":
            sort_clauses.append({"price_paise": {"order": "asc"}})
        elif normalized_sort == "price_desc":
            sort_clauses.append({"price_paise": {"order": "desc"}})
        elif normalized_sort == "name_asc":
            sort_clauses.append({"name.raw": {"order": "asc"}})
        elif normalized_sort == "newest":
            sort_clauses.append({"created_at": {"order": "desc"}})
        else:
            sort_clauses.append({"_score": {"order": "desc"}})
            sort_clauses.append({"updated_at": {"order": "desc"}})

        # Pagination offsets
        safe_page = max(1, page)
        safe_size = max(1, min(page_size, 100))
        from_offset = (safe_page - 1) * safe_size

        return {
            "from": from_offset,
            "size": safe_size,
            "query": {
                "bool": {
                    "must": must_clauses,
                    "filter": filter_clauses,
                }
            },
            "sort": sort_clauses,
            "aggs": {
                "categories": {
                    "terms": {
                        "field": "category",
                        "size": 30,
                    }
                },
                "brands": {
                    "terms": {
                        "field": "brand",
                        "size": 30,
                    }
                },
                "price_stats": {
                    "stats": {
                        "field": "price_paise",
                    }
                },
            },
        }

    def search_products(
        self,
        store_id: UUID,
        query: Optional[str] = None,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        min_price_paise: Optional[int] = None,
        max_price_paise: Optional[int] = None,
        in_stock_only: bool = True,
        sort_by: str = "relevance",
        page: int = 1,
        page_size: int = 20,
        use_nlp: bool = True,
    ) -> Dict[str, Any]:
        """
        Execute store-scoped product discovery query with optional NLP query expansion.
        """
        effective_query = query
        effective_min_price = min_price_paise
        effective_max_price = max_price_paise
        effective_in_stock = in_stock_only
        effective_sort = sort_by
        applied_nlp_filters: Dict[str, Any] = {}

        if use_nlp and query and query.strip():
            parsed_nlp = NaturalLanguageSearchParser.parse(query)
            if parsed_nlp.extracted_intents:
                effective_query = parsed_nlp.clean_query
                applied_nlp_filters = parsed_nlp.extracted_intents
                if parsed_nlp.min_price_paise is not None and effective_min_price is None:
                    effective_min_price = parsed_nlp.min_price_paise
                if parsed_nlp.max_price_paise is not None and effective_max_price is None:
                    effective_max_price = parsed_nlp.max_price_paise
                if parsed_nlp.in_stock_only is not None:
                    effective_in_stock = parsed_nlp.in_stock_only
                if parsed_nlp.sort_by is not None and (not sort_by or sort_by == "relevance"):
                    effective_sort = parsed_nlp.sort_by

        query_body = self.build_search_query(
            store_id=store_id,
            query=effective_query,
            category=category,
            brand=brand,
            min_price_paise=effective_min_price,
            max_price_paise=effective_max_price,
            in_stock_only=effective_in_stock,
            sort_by=effective_sort,
            page=page,
            page_size=page_size,
        )

        try:
            response = self.client.search(
                index=self.index_name,
                body=query_body,
            )
        except OpenSearchException as exc:
            logger.error("OpenSearch product search error: %s", exc)
            raise

        hits_data = response.get("hits", {})
        total_hits = hits_data.get("total", {})
        total_count = total_hits.get("value", 0) if isinstance(total_hits, dict) else int(total_hits)

        items = []
        for hit in hits_data.get("hits", []):
            source = hit.get("_source", {})
            source["score"] = hit.get("_score")
            items.append(source)

        # Parse aggregations
        aggs = response.get("aggregations", {})
        categories = [
            {"name": bucket.get("key"), "count": bucket.get("doc_count")}
            for bucket in aggs.get("categories", {}).get("buckets", [])
            if bucket.get("key")
        ]
        brands = [
            {"name": bucket.get("key"), "count": bucket.get("doc_count")}
            for bucket in aggs.get("brands", {}).get("buckets", [])
            if bucket.get("key")
        ]
        price_stats = aggs.get("price_stats", {})
        min_price = price_stats.get("min")
        max_price = price_stats.get("max")

        total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0

        return {
            "items": items,
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "filters": {
                "categories": categories,
                "brands": brands,
                "min_price_paise": int(min_price) if min_price is not None and not math.isnan(min_price) else 0,
                "max_price_paise": int(max_price) if max_price is not None and not math.isnan(max_price) else 0,
            },
            "applied_nlp_filters": applied_nlp_filters if applied_nlp_filters else None,
        }

    def get_suggestions(
        self,
        store_id: UUID,
        query: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Query fast edge n-gram autocomplete suggestions for a given store.
        """
        clean_q = (query or "").strip()
        if len(clean_q) < 2:
            return []

        search_body = {
            "size": max(1, min(limit, 30)),
            "query": {
                "bool": {
                    "must": [
                        {
                            "multi_match": {
                                "query": clean_q,
                                "fields": [
                                    "name.autocomplete^3",
                                    "sku^2",
                                    "brand^1.5",
                                    "category^1.5",
                                ],
                            }
                        }
                    ],
                    "filter": [
                        {"term": {"store_id": str(store_id)}},
                        {"term": {"is_active": True}},
                    ],
                }
            },
            "_source": ["id", "product_id", "sku", "name", "brand", "category", "price_paise", "qty_available", "is_in_stock"],
        }

        try:
            resp = self.client.search(index=self.index_name, body=search_body)
            hits = resp.get("hits", {}).get("hits", [])
            suggestions = []
            for hit in hits:
                src = hit.get("_source", {})
                suggestions.append({
                    "text": src.get("name"),
                    "product_id": src.get("product_id"),
                    "sku": src.get("sku"),
                    "category": src.get("category"),
                    "brand": src.get("brand"),
                    "price_paise": src.get("price_paise"),
                    "qty_available": src.get("qty_available", 0),
                    "is_in_stock": src.get("is_in_stock", False),
                })
            return suggestions
        except OpenSearchException as exc:
            logger.error("Error fetching suggestions for store_id=%s, q='%s': %s", store_id, clean_q, exc)
            return []

    def get_filter_facets(
        self,
        store_id: UUID,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retrieve available categories, brands, and price bounds for a store without returning products.
        """
        filter_clauses: List[Dict[str, Any]] = [
            {"term": {"store_id": str(store_id)}},
            {"term": {"is_active": True}},
        ]
        if category and category.strip():
            filter_clauses.append({"term": {"category": category.strip()}})

        query_body = {
            "size": 0,
            "query": {
                "bool": {
                    "filter": filter_clauses
                }
            },
            "aggs": {
                "categories": {"terms": {"field": "category", "size": 50}},
                "brands": {"terms": {"field": "brand", "size": 50}},
                "price_stats": {"stats": {"field": "price_paise"}},
            },
        }

        try:
            resp = self.client.search(index=self.index_name, body=query_body)
            aggs = resp.get("aggregations", {})
            categories = [
                {"name": b.get("key"), "count": b.get("doc_count")}
                for b in aggs.get("categories", {}).get("buckets", [])
                if b.get("key")
            ]
            brands = [
                {"name": b.get("key"), "count": b.get("doc_count")}
                for b in aggs.get("brands", {}).get("buckets", [])
                if b.get("key")
            ]
            stats = aggs.get("price_stats", {})
            min_price = stats.get("min")
            max_price = stats.get("max")
            return {
                "store_id": str(store_id),
                "categories": categories,
                "brands": brands,
                "min_price_paise": int(min_price) if min_price is not None and not math.isnan(min_price) else 0,
                "max_price_paise": int(max_price) if max_price is not None and not math.isnan(max_price) else 0,
            }
        except OpenSearchException as exc:
            logger.error("Error retrieving filter facets for store_id=%s: %s", store_id, exc)
            return {
                "store_id": str(store_id),
                "categories": [],
                "brands": [],
                "min_price_paise": 0,
                "max_price_paise": 0,
            }
