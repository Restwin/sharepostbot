"""Async SQLAlchemy engine + session factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from bot.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    """Create async engine. WAL + busy_timeout are set via event listener in init_db."""
    return create_async_engine(
        settings.db_url,
        echo=False,
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=False,
    )
