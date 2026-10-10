"""Tests for the user-reference resolution in admin /users commands."""

from __future__ import annotations

from bot.db.repo.users import UserRepository
from bot.handlers.admin_users import _parse_user_id, _resolve_target_id


async def test_resolve_target_id_by_numeric_id(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.touch(123, username="abc", first_name="A")
        await session.commit()
        assert await _resolve_target_id("123", repo) == 123


async def test_resolve_target_id_by_username_is_case_insensitive(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.touch(111, username="Restwin", first_name="Ev")
        await session.commit()
        assert await _resolve_target_id("@restwin", repo) == 111
        assert await _resolve_target_id("Restwin", repo) == 111


async def test_resolve_target_id_unknown_numeric_returns_none(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        assert await _resolve_target_id("999999", repo) is None


async def test_resolve_target_id_unknown_username_returns_none(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        assert await _resolve_target_id("@nobody", repo) is None


async def test_parse_user_id_accepts_numeric_and_at_prefix():
    assert _parse_user_id("123") == 123
    assert _parse_user_id("@123") == 123
    assert _parse_user_id("@restwin") is None
    assert _parse_user_id("") is None
