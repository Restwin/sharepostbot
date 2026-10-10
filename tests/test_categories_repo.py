"""Tests for CategoryRepository."""

from __future__ import annotations

from bot.db.repo.categories import CategoryRepository
from bot.texts import DEFAULT_POST_CATEGORIES


async def test_defaults_are_seeded(session_factory):
    async with session_factory() as session:
        repo = CategoryRepository(session)
        cats = await repo.get_active()
    assert [c.name for c in cats] == list(DEFAULT_POST_CATEGORIES)


async def test_get_active_excludes_inactive(session_factory):
    async with session_factory() as session:
        repo = CategoryRepository(session)
        cats = await repo.get_active()
        hidden_name = cats[0].name
        cats[0].is_active = False
        await session.commit()

    async with session_factory() as session:
        repo = CategoryRepository(session)
        active = [c.name for c in await repo.get_active()]
        assert hidden_name not in active


async def test_add_creates_category(session_factory):
    async with session_factory() as session:
        repo = CategoryRepository(session)
        await repo.add("Новая категория")
        await session.commit()

    async with session_factory() as session:
        repo = CategoryRepository(session)
        cat = await repo.get_by_name("новая категория")
        assert cat is not None
        assert cat.name == "Новая категория"
        assert cat.is_active is True


async def test_get_by_name_is_case_insensitive(session_factory):
    async with session_factory() as session:
        repo = CategoryRepository(session)
        assert (await repo.get_by_name("самореклама")) is not None
        assert (await repo.get_by_name("САМОРЕКЛАМА")) is not None
        assert (await repo.get_by_name("несуществующая")) is None
