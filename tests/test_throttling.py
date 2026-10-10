"""Tests for ThrottlingMiddleware: sliding-window rate limit."""

from __future__ import annotations

import asyncio

import pytest
from aiogram.types import TelegramObject

from bot.middlewares.throttling import ThrottlingMiddleware


class FakeUser:
    def __init__(self, uid: int) -> None:
        self.id = uid


async def _noop_handler(event, data):
    return "ok"


@pytest.mark.asyncio
async def test_under_limit_passes():
    mw = ThrottlingMiddleware(max_events=5, window_seconds=10)
    for _ in range(5):
        data = {"event_from_user": FakeUser(1)}
        result = await mw(_noop_handler, TelegramObject(update_id=1), data)
        assert result == "ok"


@pytest.mark.asyncio
async def test_over_limit_drops():
    mw = ThrottlingMiddleware(max_events=2, window_seconds=10)
    data = {"event_from_user": FakeUser(1)}
    assert await mw(_noop_handler, TelegramObject(update_id=1), data) == "ok"
    assert await mw(_noop_handler, TelegramObject(update_id=2), data) == "ok"
    # third call within the window is dropped (returns None)
    assert await mw(_noop_handler, TelegramObject(update_id=3), data) is None


@pytest.mark.asyncio
async def test_no_user_passes_through():
    mw = ThrottlingMiddleware()
    data = {}  # no event_from_user, e.g. channel posts
    assert await mw(_noop_handler, TelegramObject(update_id=1), data) == "ok"


@pytest.mark.asyncio
async def test_window_sliding_clears_old_entries(monkeypatch):
    """entries older than window_seconds are evicted from the bucket"""
    mw = ThrottlingMiddleware(max_events=1, window_seconds=1)
    data = {"event_from_user": FakeUser(1)}
    assert await mw(_noop_handler, TelegramObject(update_id=1), data) == "ok"
    # wait past the window; bucket is cleared on the next call
    await asyncio.sleep(1.1)
    assert await mw(_noop_handler, TelegramObject(update_id=2), data) == "ok"
