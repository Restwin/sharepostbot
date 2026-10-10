"""Tests for the post-management helpers (/myposts, /posts)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from bot.db.models import PublishedPost
from bot.handlers.posts import _parse_ids, _post_line, _post_url, _within_window


def _post(**overrides) -> PublishedPost:
    post = PublishedPost(
        author_id=1,
        author_name="Alice",
        source="pm",
        category="Другое",
        preview="some preview text",
        published_at=datetime(2026, 8, 31, 14, 0, tzinfo=UTC),
        channel_message_ids="123",
    )
    for key, value in overrides.items():
        setattr(post, key, value)
    return post


def test_parse_ids():
    assert _parse_ids("123") == [123]
    assert _parse_ids("123,456,789") == [123, 456, 789]
    assert _parse_ids(" 123 , 456 ") == [123, 456]
    assert _parse_ids("") == []
    assert _parse_ids("abc,123,xyz") == [123]


def test_within_window():
    now = datetime.now(UTC)
    assert _within_window(now - timedelta(hours=1)) is True
    assert _within_window(now - timedelta(hours=47)) is True
    assert _within_window(now - timedelta(hours=49)) is False
    assert _within_window(None) is False


def test_post_url_uses_first_channel_message_id():
    assert _post_url(_post(channel_message_ids="123,456"), -1001112223333) == (
        "https://t.me/c/1112223333/123"
    )


def test_post_url_none_without_channel_ids():
    assert _post_url(_post(channel_message_ids=""), -1001112223333) is None


def test_post_line_links_preview_and_drops_category_icon():
    line = _post_line(_post(), 1, -1001112223333)
    assert "🏷" not in line
    assert '<a href="https://t.me/c/1112223333/123">' in line
    assert "<b>1.</b>" in line
    assert "Другое" in line


def test_post_line_appends_ellipsis_when_truncated():
    long_preview = "x" * 100
    line = _post_line(_post(preview=long_preview), 1, -1001112223333)
    assert "…" in line
    # visible preview is capped, no raw overflow past the limit
    assert "x" * 61 not in line
