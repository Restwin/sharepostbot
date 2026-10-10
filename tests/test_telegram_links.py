"""Tests for telegram link parsing."""

from __future__ import annotations

from bot.utils.telegram_links import parse_chat_link


def test_parse_username_links():
    assert parse_chat_link("https://t.me/somegroup") == ("username", "somegroup")
    assert parse_chat_link("http://t.me/somegroup") == ("username", "somegroup")
    assert parse_chat_link("t.me/somegroup") == ("username", "somegroup")
    assert parse_chat_link("@somegroup") == ("username", "somegroup")


def test_parse_invite_links():
    assert parse_chat_link("https://t.me/+abc123") == ("invite", "+abc123")
    assert parse_chat_link("https://t.me/joinchat/abc123") == ("invite", "abc123")


def test_parse_invalid():
    assert parse_chat_link("") is None
    assert parse_chat_link("not a link") is None
    assert parse_chat_link("https://example.com/foo") is None
    assert parse_chat_link("https://t.me/") is None
