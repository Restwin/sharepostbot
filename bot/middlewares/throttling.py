"""Throttling middleware: per-user sliding-window rate limit.

Defaults are high enough that normal album sends (up to 10 items in one burst)
pass. Users over the limit get a short notice instead of a silent drop, and
idle buckets are pruned so the in-memory structures don't grow without bound.

A coarse safety net, not a hard anti-spam layer: limits are per-process, so
they don't persist across restarts or share across replicas.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot import texts
from bot.logging_setup import get_logger

_log = get_logger("bot.throttling")


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(
        self,
        max_events: int = 10,
        window_seconds: int = 5,
        cleanup_every: int = 1000,
    ) -> None:
        self._max = max_events
        self._window = window_seconds
        self._cleanup_every = cleanup_every
        self._buckets: dict[int, deque[float]] = {}
        self._calls = 0

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        now = time.monotonic()
        bucket = self._buckets.get(user.id)
        if bucket is None:
            bucket = self._buckets[user.id] = deque()
        bucket.append(now)
        while bucket and now - bucket[0] > self._window:
            bucket.popleft()

        if len(bucket) > self._max:
            _log.info("throttled", user_id=user.id, events=len(bucket))
            await _notify_throttled(event)
            return None

        self._maybe_prune(now)
        return await handler(event, data)

    def _maybe_prune(self, now: float) -> None:
        """Periodically drop buckets idle for longer than the window."""
        self._calls += 1
        if self._calls < self._cleanup_every:
            return
        self._calls = 0
        cutoff = now - self._window
        for user_id in [uid for uid, b in self._buckets.items() if not b or b[-1] < cutoff]:
            del self._buckets[user_id]


async def _notify_throttled(event: TelegramObject) -> None:
    """Best-effort notice; never let it break the middleware."""
    try:
        if isinstance(event, CallbackQuery):
            await event.answer(texts.THROTTLED, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(texts.THROTTLED)
    except Exception:  # noqa: S110
        pass
