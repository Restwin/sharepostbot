"""Tests for ChatRepository: lookup keyed by immutable chat_id."""

from __future__ import annotations

import pytest

from bot.db.repo.chats import ChatRepository


@pytest.mark.asyncio
async def test_add_then_lookup_by_chat_id(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        updated = await repo.add_or_update(
            chat_id=-100500, exact_name="My Group", join_link="https://t.me/+abc"
        )
        await session.commit()
        assert updated is False  # inserted

        chat = await repo.get_by_chat_id(-100500)
        assert chat is not None
        assert chat.exact_name == "My Group"
        assert chat.join_link == "https://t.me/+abc"


@pytest.mark.asyncio
async def test_add_or_update_updates_existing_by_chat_id(session_factory):
    """renaming a chat must not break lookup; chat_id is the key"""
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(
            chat_id=-100500, exact_name="Old Name", join_link="https://t.me/+old"
        )
        await session.commit()

        # same chat_id with new title and link
        updated = await repo.add_or_update(
            chat_id=-100500, exact_name="New Name", join_link="https://t.me/+new"
        )
        await session.commit()
        assert updated is True

        chat = await repo.get_by_chat_id(-100500)
        assert chat is not None
        assert chat.exact_name == "New Name"
        assert chat.join_link == "https://t.me/+new"


@pytest.mark.asyncio
async def test_lookup_by_name_still_works_for_legacy_compat(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(chat_id=-1001, exact_name="Legacy", join_link="https://t.me/+x")
        await session.commit()
        chat = await repo.get_by_name("Legacy")
        assert chat is not None
        assert chat.chat_id == -1001


@pytest.mark.asyncio
async def test_remove_by_name(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(chat_id=-1002, exact_name="To Remove", join_link="https://t.me/+y")
        await session.commit()
        await repo.remove_by_name("To Remove")
        await session.commit()
        assert await repo.get_by_chat_id(-1002) is None


@pytest.mark.asyncio
async def test_get_all_returns_sorted_by_name(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(chat_id=-1003, exact_name="Zeta", join_link="https://t.me/+z")
        await repo.add_or_update(chat_id=-1004, exact_name="Alpha", join_link="https://t.me/+a")
        await session.commit()
        chats = await repo.get_all()
        names = [c.exact_name for c in chats]
        assert names == sorted(names)


@pytest.mark.asyncio
async def test_added_by_is_recorded_on_insert(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(
            chat_id=-1005, exact_name="Owned", join_link="https://t.me/+o", added_by=42
        )
        await session.commit()
        chat = await repo.get_by_chat_id(-1005)
        assert chat is not None
        assert chat.added_by == 42


@pytest.mark.asyncio
async def test_added_by_not_overwritten_on_update(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(
            chat_id=-1006, exact_name="Keep Owner", join_link="https://t.me/+k", added_by=42
        )
        await session.commit()

        # update by another user must not clobber the original registrar
        updated = await repo.add_or_update(
            chat_id=-1006, exact_name="Keep Owner", join_link="https://t.me/+k2", added_by=99
        )
        await session.commit()
        assert updated is True
        chat = await repo.get_by_chat_id(-1006)
        assert chat is not None
        assert chat.added_by == 42


@pytest.mark.asyncio
async def test_get_by_added_by_returns_only_own_chats(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(
            chat_id=-1007, exact_name="Mine", join_link="https://t.me/+m", added_by=42
        )
        await repo.add_or_update(
            chat_id=-1008, exact_name="Yours", join_link="https://t.me/+y", added_by=7
        )
        await session.commit()

        mine = await repo.get_by_added_by(42)
        assert [c.exact_name for c in mine] == ["Mine"]


@pytest.mark.asyncio
async def test_is_blocked_defaults_false(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(chat_id=-1009, exact_name="Normal", join_link="https://t.me/+n")
        await session.commit()
        chat = await repo.get_by_chat_id(-1009)
        assert chat is not None
        assert chat.is_blocked is False


@pytest.mark.asyncio
async def test_set_blocked_records_reason_and_blocker(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(
            chat_id=-1010, exact_name="Blocked Chat", join_link="https://t.me/+b"
        )
        await session.commit()

        assert (
            await repo.set_blocked("Blocked Chat", True, block_reason="спам", blocked_by=42)
            is not None
        )
        await session.commit()
        chat = await repo.get_by_chat_id(-1010)
        assert chat is not None
        assert chat.is_blocked is True
        assert chat.block_reason == "спам"
        assert chat.blocked_by == 42

        assert await repo.set_blocked("Blocked Chat", False) is not None
        await session.commit()
        chat = await repo.get_by_chat_id(-1010)
        assert chat is not None
        assert chat.is_blocked is False
        assert chat.block_reason == ""
        assert chat.blocked_by is None

        assert await repo.set_blocked("Missing", True) is None
