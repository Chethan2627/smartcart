from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from app.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "SmartCart 2.0 Backend – Intelligent E-Commerce Platform.\n\n"
        "Engineered for multi-store retail across India with:\n"
        "- Aiven PostgreSQL: ACID transactions, row-level locking, transactional outbox\n"
        "- Aiven Apache Kafka: Asynchronous event backbone & idempotent consumers\n"
        "- Aiven OpenSearch: Typo-tolerant discovery & edge n-gram autocomplete\n\n"
        "Team: Hack Hive | Channabasaveshwara Institute of Technology (CIT), Gubbi"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS Middleware Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.get("/api/health", status_code=status.HTTP_200_OK, tags=["Health"])
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=settings.DEBUG)
