"""
OpenSearch configuration builder for SmartCart 2.0.
Resolves connection parameters, credentials, TLS settings, connection pools,
timeouts, and retry policies for Aiven OpenSearch.
"""
import logging
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from app.config import settings

logger = logging.getLogger("smartcart.opensearch.config")


class OpenSearchConfigBuilder:
    """Builder for OpenSearch client configuration dictionaries."""

    @classmethod
    def load_aiven_opensearch_env(cls) -> Dict[str, str]:
        """
        Safely inspects backend/.env.aiven for OpenSearch connection settings.
        Uses dotenv_values to read ONLY OpenSearch-related variables without altering
        os.environ, DATABASE_URL, or any PostgreSQL settings.
        """
        try:
            from app.config import BACKEND_DIR
            aiven_env_file = BACKEND_DIR / ".env.aiven"
            if not aiven_env_file.is_file():
                return {}
            from dotenv import dotenv_values
            vals = dotenv_values(str(aiven_env_file))
            os_vals: Dict[str, str] = {}
            for k, v in vals.items():
                if v and ("OPENSEARCH" in k):
                    os_vals[k] = str(v).strip()
            return os_vals
        except Exception as exc:
            logger.debug("Could not parse .env.aiven for OpenSearch: %s", exc)
            return {}

    @classmethod
    def get_client_config(
        cls,
        url: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        use_ssl: Optional[bool] = None,
        verify_certs: Optional[bool] = None,
        ca_certs: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Build configuration dictionary for opensearchpy.OpenSearch.
        Prioritizes explicit arguments over application settings, then falls back to backend/.env.aiven.
        Supports full URL strings or individual host/port/auth settings.
        """
        aiven_env = cls.load_aiven_opensearch_env()

        raw_url = (
            url
            or settings.OPENSEARCH_URL
            or aiven_env.get("OPENSEARCH_URL")
            or aiven_env.get("AIVEN_OPENSEARCH_URL")
            or aiven_env.get("AIVEN_OPENSEARCH_URI")
        )
        resolved_host = (
            host
            or settings.OPENSEARCH_HOST
            or aiven_env.get("OPENSEARCH_HOST")
            or aiven_env.get("AIVEN_OPENSEARCH_HOST")
        )

        resolved_port = port
        if resolved_port is None:
            if settings.OPENSEARCH_PORT is not None:
                resolved_port = settings.OPENSEARCH_PORT
            elif aiven_env.get("OPENSEARCH_PORT"):
                resolved_port = int(aiven_env["OPENSEARCH_PORT"])
            elif aiven_env.get("AIVEN_OPENSEARCH_PORT"):
                resolved_port = int(aiven_env["AIVEN_OPENSEARCH_PORT"])
            else:
                resolved_port = 443

        resolved_user = (
            user
            or settings.OPENSEARCH_USER
            or aiven_env.get("OPENSEARCH_USER")
            or aiven_env.get("AIVEN_OPENSEARCH_USER")
        )
        resolved_password = (
            password
            or settings.OPENSEARCH_PASSWORD
            or aiven_env.get("OPENSEARCH_PASSWORD")
            or aiven_env.get("AIVEN_OPENSEARCH_PASSWORD")
        )

        if use_ssl is not None:
            resolved_use_ssl = use_ssl
        elif settings.OPENSEARCH_USE_SSL is not None:
            resolved_use_ssl = settings.OPENSEARCH_USE_SSL
        elif "OPENSEARCH_USE_SSL" in aiven_env:
            resolved_use_ssl = aiven_env["OPENSEARCH_USE_SSL"].lower() in ("true", "1", "yes")
        elif "AIVEN_OPENSEARCH_USE_SSL" in aiven_env:
            resolved_use_ssl = aiven_env["AIVEN_OPENSEARCH_USE_SSL"].lower() in ("true", "1", "yes")
        else:
            resolved_use_ssl = True

        if verify_certs is not None:
            resolved_verify_certs = verify_certs
        elif settings.OPENSEARCH_VERIFY_CERTS is not None:
            resolved_verify_certs = settings.OPENSEARCH_VERIFY_CERTS
        elif "OPENSEARCH_VERIFY_CERTS" in aiven_env:
            resolved_verify_certs = aiven_env["OPENSEARCH_VERIFY_CERTS"].lower() in ("true", "1", "yes")
        elif "AIVEN_OPENSEARCH_VERIFY_CERTS" in aiven_env:
            resolved_verify_certs = aiven_env["AIVEN_OPENSEARCH_VERIFY_CERTS"].lower() in ("true", "1", "yes")
        else:
            resolved_verify_certs = True

        resolved_timeout = timeout if timeout is not None else settings.OPENSEARCH_TIMEOUT_SECONDS
        resolved_max_retries = max_retries if max_retries is not None else settings.OPENSEARCH_MAX_RETRIES

        # Resolve CA certificates for TLS verification
        resolved_ca_certs = ca_certs
        if resolved_ca_certs is None and resolved_use_ssl and resolved_verify_certs:
            try:
                import certifi
                resolved_ca_certs = certifi.where()
            except ImportError:
                resolved_ca_certs = None

        config: Dict[str, Any] = {
            "timeout": resolved_timeout,
            "max_retries": resolved_max_retries,
            "retry_on_timeout": True,
        }

        # If full connection URL is provided (e.g. from Aiven URI)
        if raw_url:
            parsed = urlparse(raw_url)
            hosts = [{
                "host": parsed.hostname or "localhost",
                "port": parsed.port or (443 if parsed.scheme == "https" else 9200),
            }]
            config["hosts"] = hosts
            config["use_ssl"] = parsed.scheme == "https"
            config["verify_certs"] = resolved_verify_certs
            if resolved_ca_certs and config["use_ssl"] and config["verify_certs"]:
                config["ca_certs"] = resolved_ca_certs
            if parsed.username and parsed.password:
                config["http_auth"] = (parsed.username, parsed.password)
            elif resolved_user and resolved_password:
                config["http_auth"] = (resolved_user, resolved_password)
            return config

        # Fallback to host/port settings
        hosts = [{
            "host": resolved_host or "localhost",
            "port": resolved_port,
        }]
        config["hosts"] = hosts
        config["use_ssl"] = resolved_use_ssl
        config["verify_certs"] = resolved_verify_certs
        if resolved_ca_certs and config["use_ssl"] and config["verify_certs"]:
            config["ca_certs"] = resolved_ca_certs

        if resolved_user and resolved_password:
            config["http_auth"] = (resolved_user, resolved_password)

        return config

    @classmethod
    def get_sanitized_config(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """Return a copy of the configuration dictionary with sensitive credentials masked."""
        sanitized = dict(config)
        if "http_auth" in sanitized and sanitized["http_auth"]:
            auth = sanitized["http_auth"]
            if isinstance(auth, (tuple, list)) and len(auth) >= 2:
                sanitized["http_auth"] = (auth[0], "******")
            else:
                sanitized["http_auth"] = "******"
        return sanitized

    @classmethod
    def get_index_alias(cls) -> str:
        """Return the canonical product search index alias."""
        return settings.OPENSEARCH_INDEX_ALIAS or "smartcart_products"

    @classmethod
    def get_versioned_index_name(cls, version: Optional[str] = None) -> str:
        """Return canonical versioned index name (e.g., smartcart_products_v1)."""
        ver = version or settings.OPENSEARCH_INDEX_VERSION or "v1"
        alias = cls.get_index_alias()
        return f"{alias}_{ver}"
