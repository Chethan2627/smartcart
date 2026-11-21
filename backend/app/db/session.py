import logging
from typing import AsyncGenerator, Optional
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from app.config import settings

logger = logging.getLogger(__name__)

async_engine: Optional[AsyncEngine] = None
AsyncSessionLocal: Optional[async_sessionmaker[AsyncSession]] = None


def init_db_engine() -> None:
    """
    Initializes the SQLAlchemy async engine and session factory if DATABASE_URL is configured.
    Safe to call multiple times or when DATABASE_URL is not set.
    """
    global async_engine, AsyncSessionLocal
    if not settings.DATABASE_URL:
        logger.info("DATABASE_URL is not configured; async database engine is not initialized.")
        return

    if async_engine is None:
        logger.info("Initializing SQLAlchemy asynchronous database engine.")
        async_engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
        AsyncSessionLocal = async_sessionmaker(
            bind=async_engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )


async def close_db_engine() -> None:
    """
    Properly disposes of the SQLAlchemy async engine connection pool during application shutdown.
    """
    global async_engine, AsyncSessionLocal
    if async_engine is not None:
        logger.info("Disposing SQLAlchemy asynchronous database engine connection pool.")
        await async_engine.dispose()
        async_engine = None
        AsyncSessionLocal = None


# Initialize on import if DATABASE_URL is already present in environment
if settings.DATABASE_URL:
    init_db_engine()


def async_session_maker() -> AsyncSession:
    """Helper factory returning a new AsyncSession from AsyncSessionLocal."""
    if AsyncSessionLocal is None:
        raise RuntimeError("Database is not configured. DATABASE_URL must be set in the environment.")
    return AsyncSessionLocal()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an asynchronous SQLAlchemy session.
    
    Session Lifecycle Rules:
    - Yields the session for request processing.
    - Automatically rolls back on any unhandled exception.
    - Always closes the session in a finally block to prevent connection leaks.
    - Does NOT automatically commit: commits must be explicitly managed by route or service logic.
    """
    if AsyncSessionLocal is None:
        raise RuntimeError("Database is not configured. DATABASE_URL must be set in the environment.")

    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
