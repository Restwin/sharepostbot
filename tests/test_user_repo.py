"""Tests for UserRepository: role set/get, touch, list_by_role."""

from __future__ import annotations

import pytest

from bot.db.models import RestrictMode, UserRole
from bot.db.repo.users import UserRepository


@pytest.mark.asyncio
async def test_set_role_creates_user_if_missing(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        user = await repo.set_role(123, UserRole.ALLOW)
        await session.commit()
        assert user.id == 123
        assert user.role == UserRole.ALLOW

    async with session_factory() as session:
        repo = UserRepository(session)
        assert await repo.get_role(123) == UserRole.ALLOW


@pytest.mark.asyncio
async def test_set_role_blocked_records_reason_and_mode(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.set_role(
            456,
            UserRole.BLOCKED,
            block_reason="spam",
            restrict_mode=RestrictMode.MENTION_ONLY,
            blocked_by=42,
        )
        await session.commit()

    async with session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get(456)
        assert user is not None
        assert user.role == UserRole.BLOCKED
        assert user.block_reason == "spam"
        assert user.restrict_mode == RestrictMode.MENTION_ONLY
        assert user.blocked_by == 42


@pytest.mark.asyncio
async def test_set_role_non_blocked_clears_reason(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        # block first, then allow; reason and blocker get cleared
        await repo.set_role(789, UserRole.BLOCKED, block_reason="x", blocked_by=42)
        await session.commit()

    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.set_role(789, UserRole.ALLOW)
        await session.commit()

    async with session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get(789)
        assert user is not None
        assert user.role == UserRole.ALLOW
        assert user.block_reason == ""
        assert user.blocked_by is None


@pytest.mark.asyncio
async def test_touch_creates_and_updates_profile(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        user = await repo.touch(111, username="alice", first_name="Alice")
        await session.commit()
        assert user.role == UserRole.UNKNOWN
        assert user.username == "alice"

    async with session_factory() as session:
        repo = UserRepository(session)
        # re-touch with new info: updates profile, keeps role
        user = await repo.touch(111, username="alice2", first_name="Alice2")
        await session.commit()
        assert user.username == "alice2"
        assert user.role == UserRole.UNKNOWN  # unchanged


@pytest.mark.asyncio
async def test_list_by_role(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.set_role(1, UserRole.ALLOW)
        await repo.set_role(2, UserRole.ALLOW)
        await repo.set_role(3, UserRole.BLOCKED)
        await session.commit()

    async with session_factory() as session:
        repo = UserRepository(session)
        allowed = await repo.list_by_role(UserRole.ALLOW)
        blocked = await repo.list_by_role(UserRole.BLOCKED)
        assert {u.id for u in allowed} == {1, 2}
        assert {u.id for u in blocked} == {3}


@pytest.mark.asyncio
async def test_get_role_for_missing_user_is_unknown(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        assert await repo.get_role(999999) == UserRole.UNKNOWN


@pytest.mark.asyncio
async def test_get_by_username_is_case_insensitive(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.touch(222, username="Alice", first_name="Alice")
        await session.commit()

    async with session_factory() as session:
        repo = UserRepository(session)
        assert (await repo.get_by_username("alice")) is not None
        assert (await repo.get_by_username("ALICE")) is not None
        assert (await repo.get_by_username("Alice")) is not None
        assert (await repo.get_by_username("bob")) is None
