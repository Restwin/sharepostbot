"""Tests for the /add_chat id-parsing helper."""

from __future__ import annotations

import pytest
from aiogram.types import ChatMemberLeft, ChatMemberMember, User

from bot.handlers.add_chat import _is_cancel, _parse_id, _requester_in_chat


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


class _Bot:
    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    async def get_chat_member(self, chat_id, user_id):
        if self._exc is not None:
            raise self._exc
        return self._result


async def test_requester_in_chat_member():
    bot = _Bot(result=ChatMemberMember(user=User(id=2, is_bot=False, first_name="x")))
    assert await _requester_in_chat(bot, -1001, 2) is True


async def test_requester_in_chat_left():
    bot = _Bot(result=ChatMemberLeft(user=User(id=2, is_bot=False, first_name="x")))
    assert await _requester_in_chat(bot, -1001, 2) is False


async def test_requester_in_chat_api_error():
    bot = _Bot(exc=RuntimeError("boom"))
    assert await _requester_in_chat(bot, -1001, 2) is False
