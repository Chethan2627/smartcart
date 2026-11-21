"""
OpenSearch client factory and lifecycle management for SmartCart 2.0.
Provides client instantiation, connection verification, cluster health inspection,
and clean shutdown handling.
"""
import logging
from typing import Any, Dict, Optional
from opensearchpy import OpenSearch, TransportError
from opensearchpy.exceptions import ConnectionError as OSConnectionError

from app.opensearch.config import OpenSearchConfigBuilder

logger = logging.getLogger("smartcart.opensearch.client")

_global_client: Optional[OpenSearch] = None


def create_opensearch_client(config: Optional[Dict[str, Any]] = None) -> OpenSearch:
    """
    Instantiate and configure an OpenSearch client.
    Uses OpenSearchConfigBuilder if config is omitted.
    """
    resolved_config = config or OpenSearchConfigBuilder.get_client_config()
    sanitized = OpenSearchConfigBuilder.get_sanitized_config(resolved_config)
    logger.info("Initializing OpenSearch client with configuration: %s", sanitized)

    return OpenSearch(**resolved_config)


def get_opensearch_client() -> OpenSearch:
    """
    Get or create a shared OpenSearch client instance.
    Thread-safe lazy initialization.
    """
    global _global_client
    if _global_client is None:
        _global_client = create_opensearch_client()
    return _global_client


def close_opensearch_client() -> None:
    """Close the shared OpenSearch client connection pool."""
    global _global_client
    if _global_client is not None:
        try:
            _global_client.close()
            logger.info("OpenSearch client connection closed successfully.")
        except Exception as exc:
            logger.warning("Error while closing OpenSearch client: %s", exc)
        finally:
            _global_client = None


def check_opensearch_health(client: Optional[OpenSearch] = None) -> Dict[str, Any]:
    """
    Query OpenSearch cluster health.
    Returns status dict with cluster name, status, number of nodes, and active shards.
    Catches connection errors gracefully without raising unhandled exceptions.
    """
    os_client = client or get_opensearch_client()
    try:
        health = os_client.cluster.health()
        return {
            "status": "healthy" if health.get("status") in ("green", "yellow") else "degraded",
            "cluster_name": health.get("cluster_name", "unknown"),
            "cluster_status": health.get("status", "unknown"),
            "number_of_nodes": health.get("number_of_nodes", 0),
            "active_primary_shards": health.get("active_primary_shards", 0),
            "active_shards": health.get("active_shards", 0),
            "unassigned_shards": health.get("unassigned_shards", 0),
        }
    except (OSConnectionError, TransportError) as exc:
        try:
            err_msg = str(exc)
        except Exception:
            err_msg = "OpenSearch cluster connection error"
        logger.error("OpenSearch health check failed: %s", err_msg)
        return {
            "status": "unavailable",
            "cluster_name": "unknown",
            "cluster_status": "red",
            "number_of_nodes": 0,
            "active_primary_shards": 0,
            "active_shards": 0,
            "unassigned_shards": 0,
            "error": err_msg,
        }
    except Exception as exc:
        logger.error("Unexpected error querying OpenSearch cluster health: %s", exc)
        return {
            "status": "error",
            "cluster_name": "unknown",
            "cluster_status": "red",
            "number_of_nodes": 0,
            "active_primary_shards": 0,
            "active_shards": 0,
            "unassigned_shards": 0,
            "error": str(exc),
        }
