"""
Search API endpoints for SmartCart 2.0 OpenSearch integration.
Provides:
- GET /api/v1/search/products: Store-scoped, typo-tolerant product search with NLP query expansion.
- GET /api/v1/search/suggestions: Fast edge n-gram autocomplete suggestions.
- GET /api/v1/search/filters: Aggregated category, brand, and price facet bounds for a store.
- GET /api/v1/search/health: OpenSearch cluster and index health stats (protected by Admin authorization).
"""
import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import (
    get_product_index_service,
    get_product_search_service,
    require_admin,
)
from app.models.user import User
from app.opensearch.client import check_opensearch_health
from app.opensearch.indexing import ProductIndexService
from app.opensearch.search import ProductSearchService
from app.schemas.search import (
    ProductSearchResponse,
    SearchHealthResponse,
    SearchSuggestionsResponse,
    StoreFiltersResponse,
)

logger = logging.getLogger("smartcart.api.search")

router = APIRouter(prefix="/search", tags=["Search"])


@router.get(
    "/products",
    response_model=ProductSearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Search products scoped to a specific store",
)
async def search_products(
    store_id: UUID = Query(..., description="Mandatory store ID to scope the product discovery"),
    q: Optional[str] = Query(None, description="Search keywords, SKU, product name, or natural language query"),
    category: Optional[str] = Query(None, description="Filter by category"),
    brand: Optional[str] = Query(None, description="Filter by brand"),
    min_price_paise: Optional[int] = Query(None, ge=0, description="Minimum price in paise"),
    max_price_paise: Optional[int] = Query(None, ge=0, description="Maximum price in paise"),
    in_stock_only: bool = Query(True, description="Filter only items currently in stock at this store"),
    sort_by: str = Query("relevance", description="Sort order: relevance | price_asc | price_desc | name_asc | newest"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Page size (max 100)"),
    use_nlp: bool = Query(True, description="Enable natural-language parsing for conversational queries"),
    search_service: ProductSearchService = Depends(get_product_search_service),
) -> ProductSearchResponse:
    """
    Search products with typo-tolerance, multi-field relevance boosting, store inventory scoping,
    and conversational natural-language parsing.
    """
    result = search_service.search_products(
        store_id=store_id,
        query=q,
        category=category,
        brand=brand,
        min_price_paise=min_price_paise,
        max_price_paise=max_price_paise,
        in_stock_only=in_stock_only,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
        use_nlp=use_nlp,
    )
    return ProductSearchResponse(**result)


@router.get(
    "/suggestions",
    response_model=SearchSuggestionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get autocomplete suggestions for a store",
)
async def get_search_suggestions(
    store_id: UUID = Query(..., description="Store ID for scoping suggestions"),
    q: str = Query(..., min_length=2, description="Prefix search term (min 2 characters)"),
    limit: int = Query(10, ge=1, le=30, description="Maximum suggestions to return"),
    search_service: ProductSearchService = Depends(get_product_search_service),
) -> SearchSuggestionsResponse:
    """
    Fast edge n-gram autocomplete suggestions matching products available at the specified store.
    """
    suggestions = search_service.get_suggestions(
        store_id=store_id,
        query=q,
        limit=limit,
    )
    return SearchSuggestionsResponse(suggestions=suggestions)


@router.get(
    "/filters",
    response_model=StoreFiltersResponse,
    status_code=status.HTTP_200_OK,
    summary="Get available filter facets for a store",
)
async def get_store_filters(
    store_id: UUID = Query(..., description="Store ID to inspect available filters"),
    category: Optional[str] = Query(None, description="Optional category to narrow facets"),
    search_service: ProductSearchService = Depends(get_product_search_service),
) -> StoreFiltersResponse:
    """
    Dynamic facet aggregations returning available categories, brands, and price bounds for a store.
    """
    facets = search_service.get_filter_facets(
        store_id=store_id,
        category=category,
    )
    return StoreFiltersResponse(**facets)


@router.get(
    "/health",
    response_model=SearchHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Detailed OpenSearch cluster and index health (Admin protected)",
)
async def get_search_health(
    current_admin: User = Depends(require_admin),
    index_service: ProductIndexService = Depends(get_product_index_service),
) -> SearchHealthResponse:
    """
    Retrieve OpenSearch cluster health, primary shard allocations, and index statistics.
    Protected strictly by role-based Admin authorization.
    """
    cluster_health = check_opensearch_health(index_service.client)
    index_stats = index_service.get_index_stats()

    return SearchHealthResponse(
        status=cluster_health.get("status", "unknown"),
        cluster_name=cluster_health.get("cluster_name", "unknown"),
        cluster_status=cluster_health.get("cluster_status", "unknown"),
        number_of_nodes=cluster_health.get("number_of_nodes", 0),
        active_primary_shards=cluster_health.get("active_primary_shards", 0),
        active_shards=cluster_health.get("active_shards", 0),
        unassigned_shards=cluster_health.get("unassigned_shards", 0),
        index_name=index_stats.get("index_name", index_service.index_name),
        document_count=index_stats.get("document_count", 0),
        deleted_count=index_stats.get("deleted_count", 0),
        size_in_bytes=index_stats.get("size_in_bytes", 0),
        error=cluster_health.get("error") or index_stats.get("error"),
    )
