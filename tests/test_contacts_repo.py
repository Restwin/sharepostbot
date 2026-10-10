"""Tests for AdminContactRepository: CRUD, ordering, dedup."""

from __future__ import annotations

import pytest

from bot.db.repo.contacts import AdminContactRepository


@pytest.mark.asyncio
async def test_upsert_inserts_then_updates(session_factory):
    async with session_factory() as session:
        repo = AdminContactRepository(session)
        c = await repo.upsert(user_id=111, public_role="owner", comment="hi")
        assert c.user_id == 111
        await session.commit()

    async with session_factory() as session:
        repo = AdminContactRepository(session)
        c2 = await repo.upsert(user_id=111, public_role="tech", comment="changed")
        await session.commit()
        assert c2.public_role == "tech"
        assert c2.comment == "changed"
        # same row, not a duplicate
        all_contacts = await repo.get_all()
        assert len(all_contacts) == 1


@pytest.mark.asyncio
async def test_get_all_ordered_by_display_order_then_id(session_factory):
    async with session_factory() as session:
        repo = AdminContactRepository(session)
        await repo.upsert(user_id=3, public_role="b", display_order=50)
        await repo.upsert(user_id=1, public_role="a", display_order=10)
        await repo.upsert(user_id=2, public_role="c", display_order=10)
        await session.commit()

        contacts = await repo.get_all()
        # order=10 group first (1 then 2 by id), then order=50 (3)
        assert [c.user_id for c in contacts] == [1, 2, 3]


@pytest.mark.asyncio
async def test_remove(session_factory):
    async with session_factory() as session:
        repo = AdminContactRepository(session)
        await repo.upsert(user_id=222, public_role="admin")
        await session.commit()

        await repo.remove(222)
        await session.commit()

    async with session_factory() as session:
        repo = AdminContactRepository(session)
        assert await repo.get_by_user_id(222) is None


@pytest.mark.asyncio
async def test_get_by_user_id(session_factory):
    async with session_factory() as session:
        repo = AdminContactRepository(session)
        await repo.upsert(user_id=333, public_role="mod", comment="x")
        await session.commit()

        c = await repo.get_by_user_id(333)
        assert c is not None
        assert c.public_role == "mod"
        assert c.comment == "x"
