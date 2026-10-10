"""Shared pytest fixtures."""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.db.init_db import init_db


@pytest_asyncio.fixture
async def session_factory(tmp_path):
    db_path = tmp_path / "test.sqlite"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    await init_db(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()
