"""Tests for MediaGroupCache: dedup, TTL, eviction, ordering."""

from __future__ import annotations

import pytest
from aiogram.types import Chat, Message, MessageEntity, PhotoSize, User

from bot.services.media_group_cache import MediaGroupCache, _extract_item


def _photo_msg(
    msg_id: int,
    mgid: str,
    caption: str | None = None,
    file_id: str | None = None,
) -> Message:
    return Message(
        message_id=msg_id,
        date=1,
        chat=Chat(id=-100123, type="supergroup", title="X"),
        from_user=User(id=42, is_bot=False, first_name="A"),
        media_group_id=mgid,
        photo=[PhotoSize(file_id=file_id or f"f{msg_id}", file_unique_id="u", width=10, height=10)],
        caption=caption,
    )


# MediaGroupCache.add() calls `asyncio.get_running_loop()` to arm the TTL timer,
# so all tests that exercise `add` must be async.


@pytest.mark.asyncio
async def test_add_and_get_returns_sorted_by_message_id():
    cache = MediaGroupCache()
    cache.add(_photo_msg(3, "g1"))
    cache.add(_photo_msg(1, "g1"))
    cache.add(_photo_msg(2, "g1"))
    items = cache.get("g1")
    assert items is not None
    assert [i.message_id for i in items] == [1, 2, 3]


@pytest.mark.asyncio
async def test_add_dedupes_same_message_id():
    cache = MediaGroupCache()
    cache.add(_photo_msg(1, "g1", file_id="first"))
    cache.add(_photo_msg(1, "g1", file_id="second"))  # same msg_id, ignored
    items = cache.get("g1")
    assert items is not None
    assert len(items) == 1
    assert items[0].file_id == "first"


def test_get_missing_returns_none():
    cache = MediaGroupCache()
    assert cache.get("nope") is None


def test_extract_item_returns_none_for_text_message():
    msg = Message(
        message_id=1,
        date=1,
        chat=Chat(id=1, type="private"),
        from_user=User(id=1, is_bot=False, first_name="X"),
        text="hello",
    )
    assert _extract_item(msg) is None


@pytest.mark.asyncio
async def test_cache_size_counts_distinct_albums():
    cache = MediaGroupCache()
    cache.add(_photo_msg(1, "g1"))
    cache.add(_photo_msg(2, "g1"))
    cache.add(_photo_msg(1, "g2"))
    assert cache.size() == 2


@pytest.mark.asyncio
async def test_expire_drops_entry():
    cache = MediaGroupCache()
    cache.add(_photo_msg(1, "g1"))
    assert cache.size() == 1
    cache._expire("g1")
    assert cache.size() == 0
    assert cache.get("g1") is None


@pytest.mark.asyncio
async def test_evict_if_needed_drops_oldest():
    """force over-capacity by lowering MAX_ENTRIES and adding beyond it"""
    cache = MediaGroupCache()
    cache.MAX_ENTRIES = 2  # tiny cap for the test
    cache.add(_photo_msg(1, "g1"))
    cache.add(_photo_msg(1, "g2"))
    cache.add(_photo_msg(1, "g3"))  # triggers eviction of g1 (oldest)
    assert cache.size() == 2
    assert cache.get("g1") is None  # oldest evicted
    assert cache.get("g3") is not None


@pytest.mark.asyncio
async def test_caption_rendered_as_html_preserves_entities():
    msg = Message(
        message_id=1,
        date=1,
        chat=Chat(id=-100, type="supergroup"),
        from_user=User(id=1, is_bot=False, first_name="X"),
        media_group_id="g1",
        photo=[PhotoSize(file_id="f", file_unique_id="u", width=10, height=10)],
        caption="bold text",
        caption_entities=[MessageEntity(type="bold", offset=0, length=4)],
    )
    cache = MediaGroupCache()
    cache.add(msg)
    items = cache.get("g1")
    assert items is not None
    assert "<b>bold</b>" in items[0].body_html
