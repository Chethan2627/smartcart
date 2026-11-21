"""
Aiven Kafka client configuration builder for SmartCart 2.0.
Builds secure connection parameters for KafkaProducer and KafkaConsumer supporting
both SSL (mTLS with client cert/key) and SASL_SSL / SASL_PLAINTEXT authentication.
"""
import base64
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger("smartcart.kafka.config")


class KafkaConfigBuilder:
    """Builds and validates configuration parameters for KafkaProducer and KafkaConsumer."""

    _temp_cert_dir: Optional[str] = None

    @classmethod
    def get_security_protocol(cls) -> str:
        """Return normalized security protocol (e.g. SSL, SASL_SSL, SASL_PLAINTEXT, PLAINTEXT)."""
        if settings.KAFKA_BOOTSTRAP_SERVERS:
            return (settings.KAFKA_SECURITY_PROTOCOL or "SSL").upper()
        aiven_env = cls.load_aiven_kafka_env()
        proto = aiven_env.get("KAFKA_SECURITY_PROTOCOL") or aiven_env.get("AIVEN_KAFKA_SECURITY_PROTOCOL")
        return (proto or settings.KAFKA_SECURITY_PROTOCOL or "SSL").upper()

    @classmethod
    def load_aiven_kafka_env(cls) -> Dict[str, str]:
        """
        Safely inspects backend/.env.aiven for Kafka connection settings.
        Uses dotenv_values to read ONLY Kafka-related variables without altering
        os.environ, DATABASE_URL, or any PostgreSQL settings.
        """
        try:
            from app.config import BACKEND_DIR
            aiven_env_file = BACKEND_DIR / ".env.aiven"
            if not aiven_env_file.is_file():
                return {}
            from dotenv import dotenv_values
            vals = dotenv_values(str(aiven_env_file))
            kafka_vals: Dict[str, str] = {}
            for k, v in vals.items():
                if v and ("KAFKA" in k):
                    kafka_vals[k] = str(v).strip()
            return kafka_vals
        except Exception as exc:
            logger.debug("Could not parse .env.aiven: %s", exc)
            return {}

    @classmethod
    def _resolve_existing_path(cls, path_str: Optional[str]) -> Optional[str]:
        """
        Multi-root resolution: searches for a given file path:
        1. As an absolute path.
        2. Relative to Path.cwd().
        3. Relative to BACKEND_DIR.
        4. Relative to ROOT_DIR.
        Returns the resolved absolute path as a string if found, else None.
        """
        if not path_str:
            return None
        p = Path(path_str)
        if p.is_absolute() and p.is_file():
            return str(p.resolve())
        from app.config import BACKEND_DIR, ROOT_DIR
        for base in (Path.cwd(), BACKEND_DIR, ROOT_DIR):
            candidate = base / p
            if candidate.is_file():
                return str(candidate.resolve())
        return None

    @classmethod
    def _materialize_base64_cert(cls, b64_content: str, filename: str) -> str:
        """Decode a Base64-encoded certificate/key and write it to a secure temporary file."""
        if cls._temp_cert_dir is None:
            cls._temp_cert_dir = tempfile.mkdtemp(prefix="smartcart_kafka_certs_")
        target_path = Path(cls._temp_cert_dir) / filename
        if not target_path.exists():
            decoded = base64.b64decode(b64_content)
            target_path.write_bytes(decoded)
            try:
                os.chmod(target_path, 0o600)
            except (AttributeError, OSError):
                pass
        return str(target_path)

    @classmethod
    def resolve_ssl_paths(cls) -> Dict[str, Optional[str]]:
        """
        Resolve paths to CA cert, service cert, and service key from either
        file paths or base64 environment variables with multi-root resolution.
        """
        aiven_env = cls.load_aiven_kafka_env()

        ca_path = (
            settings.KAFKA_SSL_CA_PEM_PATH
            or aiven_env.get("KAFKA_SSL_CA_PEM_PATH")
            or aiven_env.get("AIVEN_KAFKA_SSL_CA_PATH")
        )
        cert_path = (
            settings.KAFKA_SSL_CERT_PEM_PATH
            or aiven_env.get("KAFKA_SSL_CERT_PEM_PATH")
            or aiven_env.get("AIVEN_KAFKA_SSL_CERT_PATH")
        )
        key_path = (
            settings.KAFKA_SSL_KEY_PEM_PATH
            or aiven_env.get("KAFKA_SSL_KEY_PEM_PATH")
            or aiven_env.get("AIVEN_KAFKA_SSL_KEY_PATH")
        )

        if not ca_path and settings.KAFKA_SSL_CA_B64:
            ca_path = cls._materialize_base64_cert(settings.KAFKA_SSL_CA_B64, "ca.pem")

        if not cert_path and settings.KAFKA_SSL_CERT_B64:
            cert_path = cls._materialize_base64_cert(settings.KAFKA_SSL_CERT_B64, "service.cert")

        if not key_path and settings.KAFKA_SSL_KEY_B64:
            key_path = cls._materialize_base64_cert(settings.KAFKA_SSL_KEY_B64, "service.key")

        resolved_ca = cls._resolve_existing_path(ca_path)
        if not resolved_ca:
            # Multi-root fallback search in standard cert directories
            from app.config import BACKEND_DIR, ROOT_DIR
            for base in (BACKEND_DIR, ROOT_DIR, Path.cwd()):
                for fallback_name in ("ca.pem", "kafka-ca.pem"):
                    candidate = base / "certs" / fallback_name
                    if candidate.is_file():
                        resolved_ca = str(candidate.resolve())
                        break
                if resolved_ca:
                    break

        return {
            "ca_path": resolved_ca,
            "cert_path": cls._resolve_existing_path(cert_path),
            "key_path": cls._resolve_existing_path(key_path),
        }

    @classmethod
    def get_common_config(cls) -> Dict[str, Any]:
        """
        Generate base Kafka client parameters: bootstrap servers, security protocol,
        SSL certificates, and SASL authentication credentials.
        Safely falls back to backend/.env.aiven for Kafka parameters without altering PostgreSQL.
        """
        aiven_env = cls.load_aiven_kafka_env()
        protocol = cls.get_security_protocol()

        bootstrap = (
            settings.KAFKA_BOOTSTRAP_SERVERS
            or aiven_env.get("KAFKA_BOOTSTRAP_SERVERS")
            or aiven_env.get("AIVEN_KAFKA_BOOTSTRAP_SERVERS")
            or "localhost:9092"
        )

        config: Dict[str, Any] = {
            "bootstrap_servers": bootstrap,
            "security_protocol": protocol,
            "request_timeout_ms": settings.KAFKA_PRODUCER_TIMEOUT_SECONDS * 1000,
            "connections_max_idle_ms": 300000,
        }

        # Configure SSL / mTLS if applicable
        if protocol in ("SSL", "SASL_SSL"):
            ssl_paths = cls.resolve_ssl_paths()
            if ssl_paths["ca_path"]:
                config["ssl_cafile"] = ssl_paths["ca_path"]
            if ssl_paths["cert_path"]:
                config["ssl_certfile"] = ssl_paths["cert_path"]
            if ssl_paths["key_path"]:
                config["ssl_keyfile"] = ssl_paths["key_path"]

            # If no client certs are present, default to checking hostname
            config["ssl_check_hostname"] = True

        # Configure SASL if applicable
        if protocol in ("SASL_SSL", "SASL_PLAINTEXT"):
            sasl_mech = (
                settings.KAFKA_SASL_MECHANISM
                or aiven_env.get("KAFKA_SASL_MECHANISM")
                or aiven_env.get("AIVEN_KAFKA_SASL_MECHANISM")
                or "SCRAM-SHA-256"
            ).upper()
            sasl_user = (
                settings.KAFKA_SASL_USERNAME
                or aiven_env.get("KAFKA_SASL_USERNAME")
                or aiven_env.get("AIVEN_KAFKA_USERNAME")
            )
            sasl_pass = (
                settings.KAFKA_SASL_PASSWORD
                or aiven_env.get("KAFKA_SASL_PASSWORD")
                or aiven_env.get("AIVEN_KAFKA_PASSWORD")
            )

            config["sasl_mechanism"] = sasl_mech
            if sasl_user:
                config["sasl_plain_username"] = sasl_user
            if sasl_pass:
                config["sasl_plain_password"] = sasl_pass

        return config

    @classmethod
    def get_producer_config(cls) -> Dict[str, Any]:
        """Generate configuration dictionary for KafkaProducer."""
        config = cls.get_common_config()
        config.update(
            {
                "acks": "all",  # Strongest reliability guarantee: wait for all ISR ACKs
                "retries": settings.KAFKA_MAX_RETRIES,
                "retry_backoff_ms": settings.KAFKA_RETRY_BACKOFF_MS,
                "max_block_ms": settings.KAFKA_PRODUCER_TIMEOUT_SECONDS * 1000,
                "compression_type": "gzip",
            }
        )
        return config

    @classmethod
    def get_consumer_config(
        cls,
        group_id: Optional[str] = None,
        auto_offset_reset: str = "earliest",
    ) -> Dict[str, Any]:
        """
        Generate configuration dictionary for KafkaConsumer.
        Enforces enable_auto_commit=False for explicit database-first offset commits.
        """
        config = cls.get_common_config()
        session_timeout = 30000
        heartbeat_interval = 10000
        # KafkaConsumer enforces request_timeout_ms > session_timeout_ms
        request_timeout = max(config.get("request_timeout_ms", 10000), session_timeout + 10000)

        config.update(
            {
                "group_id": group_id or settings.KAFKA_CONSUMER_GROUP_ID,
                "enable_auto_commit": False,  # Manual commit ONLY after DB processing
                "auto_offset_reset": auto_offset_reset,
                "consumer_timeout_ms": settings.KAFKA_CONSUMER_TIMEOUT_MS,
                "session_timeout_ms": session_timeout,
                "heartbeat_interval_ms": heartbeat_interval,
                "request_timeout_ms": request_timeout,
            }
        )
        return config

    @classmethod
    def get_sanitized_config(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        """Return a copy of client configuration with all sensitive secrets masked for safe logging."""
        sanitized = dict(config)
        sensitive_keys = {
            "sasl_plain_password",
            "ssl_keyfile",
            "password",
            "secret",
        }
        for key in sanitized:
            if key in sensitive_keys or "password" in key or "secret" in key:
                sanitized[key] = "********"
        return sanitized
