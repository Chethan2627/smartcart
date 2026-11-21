"""
Index mappings, analysis pipelines, and schema definitions for SmartCart 2.0 OpenSearch.
Defines edge n-gram autocomplete analyzers, English stemming, lowercase normalizers,
and the Store-Product document schema.
"""
from typing import Any, Dict, Optional

INDEX_SETTINGS: Dict[str, Any] = {
    "settings": {
        "index": {
            "number_of_shards": 1,
            "number_of_replicas": 1,
            "refresh_interval": "1s",
        },
        "analysis": {
            "tokenizer": {
                "edge_ngram_tokenizer": {
                    "type": "edge_ngram",
                    "min_gram": 2,
                    "max_gram": 15,
                    "token_chars": ["letter", "digit"],
                }
            },
            "filter": {
                "english_stemmer": {
                    "type": "stemmer",
                    "language": "english",
                }
            },
            "normalizer": {
                "lowercase_normalizer": {
                    "type": "custom",
                    "filter": ["lowercase"],
                }
            },
            "analyzer": {
                "autocomplete_analyzer": {
                    "type": "custom",
                    "tokenizer": "edge_ngram_tokenizer",
                    "filter": ["lowercase"],
                },
                "autocomplete_search_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase"],
                },
                "text_search_analyzer": {
                    "type": "custom",
                    "tokenizer": "standard",
                    "filter": ["lowercase", "stop", "english_stemmer"],
                },
            },
        },
    },
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "product_id": {"type": "keyword"},
            "store_id": {"type": "keyword"},
            "sku": {
                "type": "keyword",
                "normalizer": "lowercase_normalizer",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "text_search_analyzer",
                    }
                },
            },
            "name": {
                "type": "text",
                "analyzer": "text_search_analyzer",
                "fields": {
                    "autocomplete": {
                        "type": "text",
                        "analyzer": "autocomplete_analyzer",
                        "search_analyzer": "autocomplete_search_analyzer",
                    },
                    "raw": {
                        "type": "keyword",
                        "normalizer": "lowercase_normalizer",
                    },
                },
            },
            "brand": {
                "type": "keyword",
                "normalizer": "lowercase_normalizer",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "text_search_analyzer",
                    }
                },
            },
            "category": {
                "type": "keyword",
                "normalizer": "lowercase_normalizer",
                "fields": {
                    "text": {
                        "type": "text",
                        "analyzer": "text_search_analyzer",
                    }
                },
            },
            "description": {
                "type": "text",
                "analyzer": "text_search_analyzer",
            },
            "price_paise": {"type": "long"},
            "image_url": {
                "type": "keyword",
                "index": False,
            },
            "is_active": {"type": "boolean"},
            "qty_on_hand": {"type": "integer"},
            "qty_reserved": {"type": "integer"},
            "qty_available": {"type": "integer"},
            "is_in_stock": {"type": "boolean"},
            "low_stock_threshold": {"type": "integer"},
            "created_at": {
                "type": "date",
                "format": "strict_date_optional_time||epoch_millis",
            },
            "updated_at": {
                "type": "date",
                "format": "strict_date_optional_time||epoch_millis",
            },
        }
    },
}


import copy


def get_product_index_mapping(number_of_replicas: Optional[int] = None) -> Dict[str, Any]:
    """Return the complete index configuration with settings and mappings."""
    mapping = copy.deepcopy(INDEX_SETTINGS)
    if number_of_replicas is not None:
        mapping["settings"]["index"]["number_of_replicas"] = number_of_replicas
    return mapping


def build_store_product_doc_id(product_id: Any, store_id: Any) -> str:
    """Format canonical composite document identifier: {product_id}_{store_id}."""
    return f"{str(product_id)}_{str(store_id)}"
