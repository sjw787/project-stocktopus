"""Async SQLAlchemy engine and session factory."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from stocktopus.config import get_settings

settings = get_settings()

_engine_kwargs: dict = {
    "echo": settings.env == "development",
}

if settings.lambda_runtime:
    # Lambda: each asyncio.run() call creates a new event loop.
    # NullPool ensures no connections are held between calls, avoiding
    # "Future attached to a different loop" errors.
    from sqlalchemy.pool import NullPool

    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20

engine = create_async_engine(settings.database_url, **_engine_kwargs)

AsyncSessionFactory = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session."""
    async with AsyncSessionFactory() as session:
        yield session
