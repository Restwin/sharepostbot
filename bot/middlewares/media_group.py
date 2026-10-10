"""Middleware that feeds every incoming media-group item into MediaGroupCache.

The cache is read later by:
  - repost handler (reply+mention on an album → repost the whole album)
  - wizard handler (PM album → show ONE confirm after 2s debounce)

Without this middleware, the cache would only be populated for messages that
reach a specific handler, which misses some flows.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from bot.services.media_group_cache import MediaGroupCache


class MediaGroupCacheMiddleware(BaseMiddleware):
    def __init__(self, cache: MediaGroupCache) -> None:
        self._cache = cache

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.media_group_id:
            self._cache.add(event)
        return await handler(event, data)
