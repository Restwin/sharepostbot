"""Tests for the channel-membership gate."""

from __future__ import annotations

from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
)
from aiogram.types import ChatMemberLeft, ChatMemberMember, User

from bot.config import Settings
from bot.services.membership import MembershipService


def _settings() -> Settings:
    return Settings(
        bot_token="1234567890:TESTTESTTEST",
        bot_name="testbot",
        main_channel_id=-100123,
    )


class _Bot:
    def __init__(self, member=None, chat=None, member_exc=None, chat_exc=None):
        self._member = member
        self._chat = chat
        self._member_exc = member_exc
        self._chat_exc = chat_exc
        self.chat_calls = 0

    async def get_chat_member(self, chat_id, user_id):
        if self._member_exc is not None:
            raise self._member_exc
        return self._member

    async def get_chat(self, chat_id):
        self.chat_calls += 1
        if self._chat_exc is not None:
            raise self._chat_exc
        return self._chat


async def test_member_returns_true():
    member = ChatMemberMember(user=User(id=1, is_bot=False, first_name="x"))
    service = MembershipService(_Bot(member=member), _settings())
    assert await service.is_member(1) is True


async def test_left_returns_false():
    member = ChatMemberLeft(user=User(id=1, is_bot=False, first_name="x"))
    service = MembershipService(_Bot(member=member), _settings())
    assert await service.is_member(1) is False


async def test_network_error_fails_open():
    service = MembershipService(
        _Bot(member_exc=TelegramNetworkError(method="getChatMember", message="boom")), _settings()
    )
    assert await service.is_member(1) is True


async def test_bad_request_fails_closed():
    service = MembershipService(
        _Bot(member_exc=TelegramBadRequest(method="getChatMember", message="chat not found")),
        _settings(),
    )
    assert await service.is_member(1) is False


async def test_forbidden_fails_closed():
    # 403: bot was kicked from the channel — must NOT fail open
    service = MembershipService(
        _Bot(
            member_exc=TelegramForbiddenError(
                method="getChatMember", message="bot was kicked from the channel"
            )
        ),
        _settings(),
    )
    assert await service.is_member(1) is False


async def test_bot_in_main_channel_ok():
    service = MembershipService(_Bot(chat=object()), _settings())
    assert await service.bot_in_main_channel() is True


async def test_bot_in_main_channel_missing():
    service = MembershipService(
        _Bot(chat_exc=TelegramBadRequest(method="getChat", message="chat not found")), _settings()
    )
    assert await service.bot_in_main_channel() is False


async def test_bot_in_main_channel_kicked():
    service = MembershipService(
        _Bot(
            chat_exc=TelegramForbiddenError(
                method="getChat", message="bot was kicked from the channel"
            )
        ),
        _settings(),
    )
    assert await service.bot_in_main_channel() is False


async def test_bot_in_main_channel_network_fails_open():
    service = MembershipService(
        _Bot(chat_exc=TelegramNetworkError(method="getChat", message="boom")), _settings()
    )
    assert await service.bot_in_main_channel() is True


async def test_bot_in_main_channel_cached():
    bot = _Bot(chat=object())
    service = MembershipService(bot, _settings())
    assert await service.bot_in_main_channel() is True
    assert await service.bot_in_main_channel() is True
    assert bot.chat_calls == 1


async def test_set_main_channel_state_blocks_without_api_call():
    bot = _Bot(chat=object())
    service = MembershipService(bot, _settings())
    service.set_main_channel_state(False, reason="bot removed from the main channel")
    assert await service.bot_in_main_channel() is False
    assert bot.chat_calls == 0


async def test_set_main_channel_state_restores():
    bot = _Bot(chat=object())
    service = MembershipService(bot, _settings())
    service.set_main_channel_state(False, reason="bot removed from the main channel")
    service.set_main_channel_state(True)
    assert await service.bot_in_main_channel() is True
    assert bot.chat_calls == 0
