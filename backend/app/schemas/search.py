"""
Pydantic schemas for SmartCart 2.0 OpenSearch endpoints.
Covers search results, autocomplete suggestions, facet aggregations, and cluster health.
"""
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class ProductSearchResultItem(BaseModel):
    """Single product item returned from an OpenSearch search query."""
    id: str
    product_id: UUID
    store_id: UUID
    sku: str
    name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    price_paise: int
    image_url: Optional[str] = None
    is_active: bool
    qty_on_hand: Optional[int] = 0
    qty_reserved: Optional[int] = 0
    qty_available: int = 0
    is_in_stock: bool = False
    score: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class FacetBucket(BaseModel):
    """Single aggregation bucket (category, brand, etc.)."""
    name: str
    count: int


class SearchFilterFacets(BaseModel):
    """Dynamic aggregation facets for search refinement."""
    categories: List[FacetBucket] = Field(default_factory=list)
    brands: List[FacetBucket] = Field(default_factory=list)
    min_price_paise: int = 0
    max_price_paise: int = 0


class ProductSearchResponse(BaseModel):
    """Response payload for product discovery searches."""
    items: List[ProductSearchResultItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    filters: SearchFilterFacets
    applied_nlp_filters: Optional[Dict[str, Any]] = None


class SearchSuggestionItem(BaseModel):
    """Autocomplete suggestion item."""
    text: str
    product_id: UUID
    sku: str
    category: Optional[str] = None
    brand: Optional[str] = None
    price_paise: Optional[int] = None
    qty_available: Optional[int] = None
    is_in_stock: Optional[bool] = None


class SearchSuggestionsResponse(BaseModel):
    """Response payload for autocomplete suggestions."""
    suggestions: List[SearchSuggestionItem]


class StoreFiltersResponse(BaseModel):
    """Response payload for store-specific available search filters."""
    store_id: UUID
    categories: List[FacetBucket]
    brands: List[FacetBucket]
    min_price_paise: int
    max_price_paise: int


class SearchHealthResponse(BaseModel):
    """Detailed cluster and index health response (protected for Admin users)."""
    status: str
    cluster_name: str
    cluster_status: str
    number_of_nodes: int
    active_primary_shards: int
    active_shards: int
    unassigned_shards: int
    index_name: str
    document_count: int
    deleted_count: int
    size_in_bytes: int
    error: Optional[str] = None
