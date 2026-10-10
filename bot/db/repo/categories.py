"""PostCategory repository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import PostCategory


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self) -> list[PostCategory]:
        stmt = (
            select(PostCategory)
            .where(PostCategory.is_active.is_(True))
            .order_by(PostCategory.display_order, PostCategory.id)
        )
        result = await self._session.scalars(stmt)
        return list(result)

    async def get_all(self) -> list[PostCategory]:
        stmt = select(PostCategory).order_by(PostCategory.display_order, PostCategory.id)
        result = await self._session.scalars(stmt)
        return list(result)

    async def get_by_id(self, category_id: int) -> PostCategory | None:
        return await self._session.get(PostCategory, category_id)

    async def get_by_name(self, name: str) -> PostCategory | None:
        # SQLite's LOWER() is ASCII-only and would not fold Cyrillic, so compare
        # casefolded names in Python; the category list is tiny.
        target = name.casefold()
        result = await self._session.scalars(select(PostCategory))
        for category in result:
            if category.name.casefold() == target:
                return category
        return None

    async def add(self, name: str, *, display_order: int | None = None) -> PostCategory:
        if display_order is None:
            display_order = await self._next_order()
        category = PostCategory(name=name, display_order=display_order, is_active=True)
        self._session.add(category)
        return category

    async def _next_order(self) -> int:
        stmt = select(func.max(PostCategory.display_order))
        current = await self._session.scalar(stmt)
        return (current or 0) + 1
