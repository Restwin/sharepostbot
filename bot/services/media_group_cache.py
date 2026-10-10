"""In-memory cache of media group items, keyed by media_group_id.

Telegram delivers an album as separate updates sharing the same
`media_group_id`; this cache collects them so a reply+mention on any album
item reposts the whole album, and the PM wizard can show one confirm after a
2s debounce.

Only album items are cached, so the size tracks album traffic, not total
message traffic.

Bounds:
- TTL: entries expire after 1 hour (via asyncio.call_later).
- MAX_ENTRIES: 5000 albums; oldest evicted first. At ~4 items/album that is
  ~20k CachedMediaItem objects, a few MB.
- in-process only: lost on bot restart (falls back to single-item repost).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from aiogram.types import Message
from aiogram.utils.text_decorations import HtmlDecoration


@dataclass(slots=True)
class CachedMediaItem:
    message_id: int
    file_id: str
    media_type: Literal["photo", "video", "document"]
    body_html: str  # HTML-rendered caption (empty if no caption on this item)


class MediaGroupCache:
    TTL_SECONDS = 3600  # 1 hour
    MAX_ENTRIES = 5000  # hard cap on number of distinct albums in cache

    def __init__(self) -> None:
        # insert order doubles as eviction order; oldest album is the first key
        self._items: dict[str, list[CachedMediaItem]] = {}
        self._timers: dict[str, asyncio.TimerHandle] = {}

    def add(self, message: Message) -> None:
        mgid = message.media_group_id
        if mgid is None:
            return

        item = _extract_item(message)
        if item is None:
            return

        # setdefault keeps insertion order: new albums go to the end
        bucket = self._items.setdefault(mgid, [])
        # Telegram sometimes redelivers updates; avoid duplicates
        if not any(i.message_id == item.message_id for i in bucket):
            bucket.append(item)

        self._reset_timer(mgid)
        self._evict_if_needed()

    def get(self, media_group_id: str) -> list[CachedMediaItem] | None:
        bucket = self._items.get(media_group_id)
        if bucket is None:
            return None
        return sorted(bucket, key=lambda i: i.message_id)

    def _reset_timer(self, mgid: str) -> None:
        old = self._timers.get(mgid)
        if old is not None:
            old.cancel()
        loop = asyncio.get_running_loop()
        self._timers[mgid] = loop.call_later(self.TTL_SECONDS, lambda: self._expire(mgid))

    def _expire(self, mgid: str) -> None:
        self._items.pop(mgid, None)
        self._timers.pop(mgid, None)

    def _evict_if_needed(self) -> None:
        """Evict the oldest albums when over MAX_ENTRIES."""
        while len(self._items) > self.MAX_ENTRIES:
            oldest_mgid = next(iter(self._items))
            self._expire(oldest_mgid)

    def size(self) -> int:
        """Number of distinct albums currently in cache."""
        return len(self._items)


def _render_caption(message: Message) -> str:
    if not message.caption:
        return ""
    return HtmlDecoration().unparse(text=message.caption, entities=message.caption_entities or [])


def _extract_item(message: Message) -> CachedMediaItem | None:
    body_html = _render_caption(message)
    if message.photo:
        largest = max(message.photo, key=lambda p: p.file_size or 0)
        return CachedMediaItem(
            message_id=message.message_id,
            file_id=largest.file_id,
            media_type="photo",
            body_html=body_html,
        )
    if message.video:
        return CachedMediaItem(
            message_id=message.message_id,
            file_id=message.video.file_id,
            media_type="video",
            body_html=body_html,
        )
    if message.document:
        return CachedMediaItem(
            message_id=message.message_id,
            file_id=message.document.file_id,
            media_type="document",
            body_html=body_html,
        )
    return None
