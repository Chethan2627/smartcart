import time
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.api.v1.api import api_router
from app.core.error_handlers import register_exception_handlers
from app.db.session import init_db_engine, close_db_engine, AsyncSessionLocal

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager:
    - Initializes the database engine on startup if DATABASE_URL is configured.
    - Properly disposes of the database engine pool on shutdown.
    """
    logger.info("Starting up %s (environment=%s)", settings.APP_NAME, settings.ENVIRONMENT)
    init_db_engine()
    yield
    logger.info("Shutting down %s...", settings.APP_NAME)
    await close_db_engine()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "SmartCart 2.0 Backend – Intelligent E-Commerce Platform.\n\n"
        "Engineered for multi-store retail across India with:\n"
        "- PostgreSQL: ACID transactions, row-level locking, transactional outbox\n"
        "- Apache Kafka: Asynchronous event backbone & idempotent consumers\n"
        "- OpenSearch: Typo-tolerant discovery & edge n-gram autocomplete\n\n"
        "Team: Hack Hive | Channabasaveshwara Institute of Technology (CIT), Gubbi"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Register centralized exception handlers
register_exception_handlers(app)

# CORS Middleware Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Centralized API Version 1 Router
app.include_router(api_router, prefix="/api/v1")


@app.get("/", tags=["Root"])
@app.get("/api", tags=["Root"])
async def root():
    """Root endpoint welcoming clients and confirming service status."""
    return {
        "project": "SmartCart 2.0",
        "tagline": "Smarter Discovery. Reliable Inventory. Seamless Shopping.",
        "team": "Hack Hive",
        "institution": "Channabasaveshwara Institute of Technology (CIT), Gubbi",
        "status": "online",
        "docs_url": "/docs",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health", status_code=status.HTTP_200_OK, tags=["Health"])
@app.get("/api/health", status_code=status.HTTP_200_OK, tags=["Health"])
@app.get("/api/v1/health", status_code=status.HTTP_200_OK, tags=["Health"])
async def health_check():
    """
    Health check endpoint returning system status and service connection configuration readiness.
    Used by frontend, Docker, and monitoring platforms.
    """
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": settings.APP_VERSION,
        "services": {
            "postgresql_configured": bool(settings.DATABASE_URL),
            "kafka_configured": bool(settings.KAFKA_BOOTSTRAP_SERVERS),
            "opensearch_configured": bool(settings.OPENSEARCH_HOST),
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/health/db", status_code=status.HTTP_200_OK, tags=["Health"])
@app.get("/api/health/db", status_code=status.HTTP_200_OK, tags=["Health"])
@app.get("/api/v1/health/db", status_code=status.HTTP_200_OK, tags=["Health"])
async def database_health_check(response: Response):
    """
    Database health check verifying live PostgreSQL connectivity via SELECT 1.
    - Returns HTTP 200 with query latency on success.
    - Returns HTTP 503 if PostgreSQL is unconfigured or unreachable.
    - Sanitizes all errors: never leaks credentials or raw exception messages.
    - Detailed errors logged internally.
    """
    if not settings.DATABASE_URL or AsyncSessionLocal is None:
        logger.warning("Database health check requested but database is not configured.")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "database": "postgresql",
            "database_connected": False,
            "error": "Database service is not configured",
            "timestamp": datetime.utcnow().isoformat(),
        }

    start_time = time.perf_counter()
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("SELECT 1;"))
            result.scalar_one()

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return {
            "status": "healthy",
            "database": "postgresql",
            "database_connected": True,
            "latency_ms": latency_ms,
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as exc:
        logger.error("Database health check query failed: %s", exc, exc_info=True)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "database": "postgresql",
            "database_connected": False,
            "error": "Database connectivity check failed",
            "timestamp": datetime.utcnow().isoformat(),
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=settings.DEBUG)
