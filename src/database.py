"""
Database connection and session management.
Handles PostgreSQL async connection via SQLAlchemy.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool, QueuePool
import logging

from src.config import get_settings

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────
# Database Engine & Session
# ─────────────────────────────────────────────────────────────
_engine: AsyncEngine | None = None
_async_session_maker = None

# Base class for all ORM models
Base = declarative_base()


def get_engine() -> AsyncEngine:
    """
    Get or create async database engine.
    
    Returns:
        AsyncEngine: SQLAlchemy async engine
    """
    global _engine
    if _engine is None:
        settings = get_settings()
        
        # Use NullPool for development, QueuePool for production
        pool_class = NullPool if settings.DEBUG else QueuePool
        
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DATABASE_ECHO,
            pool_class=pool_class,
            pool_size=settings.DATABASE_POOL_SIZE,
            max_overflow=settings.DATABASE_MAX_OVERFLOW,
            pool_pre_ping=True,  # Verify connections before using
        )
    return _engine


def get_async_session_maker():
    """
    Get or create async session maker.
    
    Returns:
        async_sessionmaker: Session factory
    """
    global _async_session_maker
    if _async_session_maker is None:
        engine = get_engine()
        _async_session_maker = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_maker


async def get_session() -> AsyncSession:
    """
    FastAPI dependency: get database session.
    
    Yields:
        AsyncSession: Database session
        
    Example:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_session)):
            ...
    """
    session_maker = get_async_session_maker()
    async with session_maker() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            await session.close()


async def create_all_tables() -> None:
    """
    Create all tables in database.
    Called once at app startup.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("✅ Database tables created")


async def drop_all_tables() -> None:
    """
    Drop all tables from database.
    CAUTION: Only use for testing!
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.warning("⚠️ All database tables dropped")


async def close_db() -> None:
    """
    Close database connection.
    Called on app shutdown.
    """
    engine = get_engine()
    await engine.dispose()
    logger.info("✅ Database connection closed")