"""registration_hint: appendix for reposts from unregistered chats."""

from __future__ import annotations

from bot import texts
from bot.db.models import SavedChat
from bot.handlers.repost import registration_hint


def test_no_row_gives_hint():
    assert texts.CHAT_NOT_REGISTERED_HINT in registration_hint(None)


def test_registered_with_link_has_no_hint():
    saved = SavedChat(chat_id=-1001, exact_name="Chat", join_link="https://t.me/+abc")
    assert registration_hint(saved) == ""


def test_registered_without_link_gives_hint():
    saved = SavedChat(chat_id=-1002, exact_name="Chat", join_link="")
    assert texts.CHAT_NOT_REGISTERED_HINT in registration_hint(saved)
