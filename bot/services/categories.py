"""Shared helpers for reading active post categories."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.db.repo.categories import CategoryRepository


async def active_categories(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[tuple[int, str]]:
    """Return the active post categories as (id, name) pairs, in display order."""
    async with session_factory() as session:
        repo = CategoryRepository(session)
        cats = await repo.get_active()
        return [(c.id, c.name) for c in cats]
