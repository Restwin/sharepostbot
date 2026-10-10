"""Tests for the PM fallback filter.

`pm_fallback` is a catch-all and must not match command messages: if it did,
aiogram would stop propagation and the command handlers in later routers
(access, wizard, add_chat) would never run.
"""

from __future__ import annotations

import pytest
from aiogram.types import Chat, Message, User

from bot.handlers.common import _PM_NON_COMMAND_TEXT


def _msg(text: str | None, chat_type: str = "private") -> Message:
    return Message(
        message_id=1,
        date=1,
        chat=Chat(id=1, type=chat_type),
        from_user=User(id=1, is_bot=False, first_name="A"),
        text=text,
    )


@pytest.mark.parametrize("text", ["hello", "привет", "123", "текст с / слэшем внутри"])
def test_pm_fallback_filter_accepts_plain_text(text):
    assert _PM_NON_COMMAND_TEXT.resolve(_msg(text))


@pytest.mark.parametrize(
    "text",
    [
        "/contacts",
        "/post",
        "/whyblocked",
        "/add_chat",
        "/start",
        "/menu",
        "/help",
        "/cancel",
    ],
)
def test_pm_fallback_filter_rejects_commands(text):
    assert not _PM_NON_COMMAND_TEXT.resolve(_msg(text))


def test_pm_fallback_filter_rejects_empty_and_media_text():
    assert not _PM_NON_COMMAND_TEXT.resolve(_msg(""))
    assert not _PM_NON_COMMAND_TEXT.resolve(_msg(None))


def test_pm_fallback_filter_rejects_non_private_chats():
    assert not _PM_NON_COMMAND_TEXT.resolve(_msg("hello", chat_type="group"))
