"""Tests for the /add_chat id-parsing helper."""

from __future__ import annotations

import pytest

from bot.handlers.add_chat import _is_cancel, _parse_id


@pytest.mark.parametrize(
    "text,expected_id",
    [
        ("-1001234567890", -1001234567890),
        ("Мой чат | -1001234567890", -1001234567890),
        ("id: -1001234567890", -1001234567890),
        ("Чат 2026: -1001234567890", -1001234567890),
        ("-1001234567890 лишнее", -1001234567890),
    ],
)
def test_parse_id(text, expected_id):
    assert _parse_id(text) == expected_id


@pytest.mark.parametrize(
    "text",
    [
        "",
        "Нет чисел тут",
        "Просто название",
        "abc",
    ],
)
def test_parse_id_no_number(text):
    assert _parse_id(text) is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("/cancel", True),
        ("/cancel@SomeBot", True),
        ("/help", False),
        ("/add_chat", False),
        ("", False),
    ],
)
def test_is_cancel(text, expected):
    assert _is_cancel(text) is expected
