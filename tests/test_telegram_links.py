"""Tests for telegram link parsing."""

from __future__ import annotations

import pytest

from bot.utils.telegram_links import parse_chat_link


def test_parse_username_links():
    assert parse_chat_link("https://t.me/somegroup") == ("username", "somegroup")
    assert parse_chat_link("http://t.me/somegroup") == ("username", "somegroup")
    assert parse_chat_link("t.me/somegroup") == ("username", "somegroup")
    assert parse_chat_link("@somegroup") == ("username", "somegroup")
    assert parse_chat_link("@Some_Group_2024") == ("username", "Some_Group_2024")


def test_parse_invite_links():
    assert parse_chat_link("https://t.me/+abcdefghijklmnopqrstuvwxyz") == (
        "invite",
        "+abcdefghijklmnopqrstuvwxyz",
    )
    assert parse_chat_link("https://t.me/joinchat/abcdefghijklmnopqrstuvwxyz") == (
        "invite",
        "abcdefghijklmnopqrstuvwxyz",
    )
    assert parse_chat_link("https://t.me/+AAbb-1122_CCdd3344") == (
        "invite",
        "+AAbb-1122_CCdd3344",
    )


@pytest.mark.parametrize(
    "link",
    [
        "",
        "not a link",
        "https://example.com/foo",
        "https://t.me/",
        # query strings turn chat links into action links — rejected
        "https://t.me/proxy?server=1.2.3.4&port=443&secret=abc",
        "https://t.me/socks?server=1.2.3.4&port=443",
        "https://t.me/share/url?url=https://example.com",
        "https://t.me/somegroup?start=param",
        # fragments
        "https://t.me/somegroup#fragment",
        # invite hash too short
        "https://t.me/+abc123",
        "https://t.me/joinchat/abc",
        # malformed usernames
        "https://t.me/ab",
        "https://t.me/some group",
        "https://t.me/user$name",
        "@ab",
    ],
)
def test_parse_invalid(link):
    assert parse_chat_link(link) is None
