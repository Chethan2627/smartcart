from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


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

    # Aiven Apache Kafka (SSL)
    KAFKA_BOOTSTRAP_SERVERS: Optional[str] = None
    KAFKA_SECURITY_PROTOCOL: str = "SSL"
    KAFKA_SSL_CA_PEM_PATH: Optional[str] = None
    KAFKA_SSL_CERT_PEM_PATH: Optional[str] = None
    KAFKA_SSL_KEY_PEM_PATH: Optional[str] = None
    KAFKA_SSL_CA_B64: Optional[str] = None
    KAFKA_SSL_CERT_B64: Optional[str] = None
    KAFKA_SSL_KEY_B64: Optional[str] = None

    # Kafka Topic Names
    KAFKA_TOPIC_ORDER_PLACED: str = "order.placed"
    KAFKA_TOPIC_ORDER_CANCELLED: str = "order.cancelled"
    KAFKA_TOPIC_INVENTORY_CHANGED: str = "inventory.changed"
    KAFKA_TOPIC_PRODUCT_CHANGED: str = "product.changed"
    KAFKA_TOPIC_SEARCH_EVENTS: str = "search.events"
    KAFKA_TOPIC_ORDER_PLACED_DLQ: str = "order.placed.dlq"

    # Aiven OpenSearch
    OPENSEARCH_HOST: Optional[str] = None
    OPENSEARCH_PORT: int = 443
    OPENSEARCH_USER: Optional[str] = None
    OPENSEARCH_PASSWORD: Optional[str] = None
    OPENSEARCH_USE_SSL: bool = True
    OPENSEARCH_VERIFY_CERTS: bool = True
    OPENSEARCH_INDEX_PRODUCTS: str = "smartcart_products"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
