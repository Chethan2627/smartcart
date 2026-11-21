from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import AliasChoices, Field

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
ENV_FILES = (
    str(ROOT_DIR / ".env"),
    str(BACKEND_DIR / ".env"),
)


class Settings(BaseSettings):
    # Application Info
    APP_NAME: str = "SmartCart 2.0"
    APP_VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # CORS Configuration
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    # JWT Authentication
    JWT_SECRET_KEY: str = Field(
        default="smartcart-development-secret-key-at-least-32-chars-long",
        description="JWT Secret signing key",
    )
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Aiven PostgreSQL Database
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description="Aiven PostgreSQL Async connection URL (postgresql+asyncpg://...)",
    )
    DATABASE_SYNC_URL: Optional[str] = Field(
        default=None,
        description="Aiven PostgreSQL Sync connection URL for Alembic",
    )

    # Aiven Apache Kafka (SSL / SASL)
    KAFKA_BOOTSTRAP_SERVERS: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("KAFKA_BOOTSTRAP_SERVERS", "AIVEN_KAFKA_BOOTSTRAP_SERVERS"),
    )
    KAFKA_SECURITY_PROTOCOL: str = Field(
        default="SSL",
        validation_alias=AliasChoices("KAFKA_SECURITY_PROTOCOL", "AIVEN_KAFKA_SECURITY_PROTOCOL"),
    )
    KAFKA_SASL_MECHANISM: str = Field(
        default="SCRAM-SHA-256",
        validation_alias=AliasChoices("KAFKA_SASL_MECHANISM", "AIVEN_KAFKA_SASL_MECHANISM"),
    )
    KAFKA_SASL_USERNAME: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("KAFKA_SASL_USERNAME", "AIVEN_KAFKA_USERNAME"),
    )
    KAFKA_SASL_PASSWORD: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("KAFKA_SASL_PASSWORD", "AIVEN_KAFKA_PASSWORD"),
    )
    KAFKA_SSL_CA_PEM_PATH: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("KAFKA_SSL_CA_PEM_PATH", "AIVEN_KAFKA_SSL_CA_PATH"),
    )
    KAFKA_SSL_CERT_PEM_PATH: Optional[str] = None
    KAFKA_SSL_KEY_PEM_PATH: Optional[str] = None
    KAFKA_SSL_CA_B64: Optional[str] = None
    KAFKA_SSL_CERT_B64: Optional[str] = None
    KAFKA_SSL_KEY_B64: Optional[str] = None

    # Kafka Consumer & Producer Settings
    KAFKA_CONSUMER_GROUP_ID: str = "smartcart-orders-consumer-group"
    KAFKA_PRODUCER_TIMEOUT_SECONDS: int = 10
    KAFKA_CONSUMER_TIMEOUT_MS: int = 1000
    KAFKA_MAX_RETRIES: int = 5
    KAFKA_RETRY_BACKOFF_MS: int = 500

    # Kafka Canonical Topics
    KAFKA_TOPIC_ORDERS: str = "smartcart.orders"
    KAFKA_TOPIC_INVENTORY: str = "smartcart.inventory"
    KAFKA_TOPIC_PRODUCTS: str = "smartcart.products"
    KAFKA_TOPIC_DLQ: str = "smartcart.dlq"

    # Kafka Topic Legacy Aliases
    KAFKA_TOPIC_ORDER_PLACED: str = "smartcart.orders"
    KAFKA_TOPIC_ORDER_CANCELLED: str = "smartcart.orders"
    KAFKA_TOPIC_INVENTORY_CHANGED: str = "smartcart.inventory"
    KAFKA_TOPIC_PRODUCT_CHANGED: str = "smartcart.products"
    KAFKA_TOPIC_SEARCH_EVENTS: str = "smartcart.search"
    KAFKA_TOPIC_ORDER_PLACED_DLQ: str = "smartcart.dlq"

    # Aiven OpenSearch
    OPENSEARCH_HOST: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OPENSEARCH_HOST", "AIVEN_OPENSEARCH_HOST"),
    )
    OPENSEARCH_PORT: Optional[int] = Field(
        default=None,
        validation_alias=AliasChoices("OPENSEARCH_PORT", "AIVEN_OPENSEARCH_PORT"),
    )
    OPENSEARCH_USER: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OPENSEARCH_USER", "AIVEN_OPENSEARCH_USER"),
    )
    OPENSEARCH_PASSWORD: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OPENSEARCH_PASSWORD", "AIVEN_OPENSEARCH_PASSWORD"),
    )
    OPENSEARCH_URL: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OPENSEARCH_URL", "AIVEN_OPENSEARCH_URL", "AIVEN_OPENSEARCH_URI"),
    )
    OPENSEARCH_USE_SSL: bool = Field(
        default=True,
        validation_alias=AliasChoices("OPENSEARCH_USE_SSL", "AIVEN_OPENSEARCH_USE_SSL"),
    )
    OPENSEARCH_VERIFY_CERTS: bool = Field(
        default=True,
        validation_alias=AliasChoices("OPENSEARCH_VERIFY_CERTS", "AIVEN_OPENSEARCH_VERIFY_CERTS"),
    )
    OPENSEARCH_TIMEOUT_SECONDS: int = 10
    OPENSEARCH_MAX_RETRIES: int = 3
    OPENSEARCH_INDEX_ALIAS: str = "smartcart_products"
    OPENSEARCH_INDEX_VERSION: str = "v1"
    OPENSEARCH_INDEX_PRODUCTS: str = "smartcart_products"

    # Cloudinary Image Storage
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None
    CLOUDINARY_URL: Optional[str] = None
    CLOUDINARY_UPLOAD_FOLDER: str = "smartcart/products"

    model_config = SettingsConfigDict(
        env_file=ENV_FILES,
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
