"""
Database configuration - SQLAlchemy async engine and session management
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from core.config import settings

# Create async engine
if settings.db_url.startswith('sqlite'):
    # SQLite doesn't support pool_size/max_overflow
    engine = create_async_engine(
        settings.db_url,
        echo=settings.app.debug,
        future=True,
    )
else:
    engine = create_async_engine(
        settings.db_url,
        echo=settings.app.debug,
        future=True,
        pool_size=10,
        max_overflow=20,
    )

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)

# Base class for models
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get database session"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connections"""
    await engine.dispose()
