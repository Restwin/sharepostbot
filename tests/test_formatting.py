"""Tests for utils.telegram_links and utils.formatting."""

from __future__ import annotations

from bot.utils.formatting import (
    html_escape,
    make_preview,
    strip_html,
)
from bot.utils.telegram_links import (
    is_valid_invite_link,
    post_link,
    public_chat_link,
)


def test_html_escape_escapes_angle_brackets_and_amp():
    assert html_escape("a<b>&c") == "a&lt;b&gt;&amp;c"
    assert html_escape(None) == ""  # type: ignore[arg-type]


def test_post_link_supergroup_strips_minus_100_prefix():
    assert post_link(-1001234567890, 42) == "https://t.me/c/1234567890/42"


def test_post_link_plain_negative_id():
    assert post_link(-123, 1) == "https://t.me/c/123/1"


def test_public_chat_link_strips_at_prefix():
    assert public_chat_link("@mygroup") == "https://t.me/mygroup"
    assert public_chat_link("mygroup") == "https://t.me/mygroup"


def test_is_valid_invite_link():
    assert is_valid_invite_link("https://t.me/joinchat/abc")
    assert is_valid_invite_link("https://t.me/+abc")
    assert not is_valid_invite_link("https://t.me/mygroup")
    assert not is_valid_invite_link("https://example.com/x")


def test_strip_html_removes_tags_and_unescapes():
    assert strip_html("<b>Привет</b> &amp; <i>мир</i>") == "Привет & мир"


def test_make_preview_truncates():
    assert make_preview("<b>" + "x" * 100 + "</b>", limit=5) == "xxxxx"
    assert make_preview(None) == ""
    assert make_preview("") == ""
