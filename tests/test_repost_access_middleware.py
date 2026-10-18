"""Tests for the repost access middleware: trigger phrases are gated too."""

from __future__ import annotations

from datetime import datetime

import pytest
from aiogram.enums import ChatType
from aiogram.types import Chat, Message, MessageEntity, User

from bot.config import Settings
from bot.db.models import RestrictMode, UserRole
from bot.db.repo.users import UserRepository
from bot.middlewares.access import RepostAccessMiddleware
from bot.services.access import AccessService


def _settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        bot_token="1234567890:AAA-test",
        bot_name="testbot",
        main_channel_id=-100,
        admin_ids=[],
        repost_trigger_phrases=["в движухи"],
    )


class FakeMembership:
    def __init__(self, *, in_channel: bool = True) -> None:
        self._in_channel = in_channel

    async def is_member(self, user_id: int) -> bool:
        return False

    async def bot_in_main_channel(self) -> bool:
        return self._in_channel


def _message(text: str, entities: list[MessageEntity] | None = None) -> Message:
    chat = Chat(id=-100123, type=ChatType.GROUP)
    source = Message(message_id=2, date=datetime.now(), chat=chat, text="orig")
    return Message(
        message_id=1,
        date=datetime.now(),
        chat=chat,
        from_user=User(id=333, is_bot=False, first_name="Bob"),
        text=text,
        entities=entities,
        reply_to_message=source,
    )


async def _block_user(session_factory) -> None:
    async with session_factory() as session:
        await UserRepository(session).set_role(
            333,
            UserRole.BLOCKED,
            block_reason="spam",
            restrict_mode=RestrictMode.BOTH,
        )
        await session.commit()


def _fake_temp_reply(replies: list[str]):
    async def fake(message, text, **kwargs):
        replies.append(text)

    return fake


@pytest.mark.asyncio
async def test_trigger_phrase_is_gated_for_blocked_user(session_factory, monkeypatch):
    await _block_user(session_factory)
    mw = RepostAccessMiddleware(
        AccessService(_settings(), session_factory),
        FakeMembership(),
        session_factory,
        _settings(),
    )

    replies: list[str] = []
    monkeypatch.setattr("bot.middlewares.access.temp_reply", _fake_temp_reply(replies))
    called: list[int] = []

    async def handler(event, data):
        called.append(1)

    await mw(handler, _message("В движухи!"), {})
    assert not called
    assert replies, "deny reply expected"


@pytest.mark.asyncio
async def test_plain_reply_passes_through(session_factory, monkeypatch):
    mw = RepostAccessMiddleware(
        AccessService(_settings(), session_factory),
        FakeMembership(),
        session_factory,
        _settings(),
    )
    called: list[int] = []

    async def handler(event, data):
        called.append(1)

    await mw(handler, _message("обычный комментарий"), {})
    assert called == [1]


@pytest.mark.asyncio
async def test_mention_still_gated(session_factory, monkeypatch):
    await _block_user(session_factory)
    mw = RepostAccessMiddleware(
        AccessService(_settings(), session_factory),
        FakeMembership(),
        session_factory,
        _settings(),
    )
    replies: list[str] = []
    monkeypatch.setattr("bot.middlewares.access.temp_reply", _fake_temp_reply(replies))
    called: list[int] = []

    async def handler(event, data):
        called.append(1)

    mention = MessageEntity(type="mention", offset=0, length=8)
    await mw(handler, _message("@testbot", entities=[mention]), {})
    assert not called
    assert replies, "deny reply expected"


@pytest.mark.asyncio
async def test_publish_blocked_when_bot_not_in_main_channel(session_factory, monkeypatch):
    mw = RepostAccessMiddleware(
        AccessService(_settings(), session_factory),
        FakeMembership(in_channel=False),
        session_factory,
        _settings(),
    )
    replies: list[str] = []
    monkeypatch.setattr("bot.middlewares.access.temp_reply", _fake_temp_reply(replies))
    called: list[int] = []

    async def handler(event, data):
        called.append(1)

    mention = MessageEntity(type="mention", offset=0, length=8)
    await mw(handler, _message("@testbot", entities=[mention]), {})
    assert not called
    assert replies, "deny reply expected"
    assert "главному каналу" in replies[0]
