"""Guest gate: hide all commands from non-members of the main channel.

A "guest" is a user who is neither STAFF nor a member of
`Settings.main_channel_id`: someone who found the bot but does not belong to
the community. Guests may only use `/start` and `/recheck` (which show the
guest message with admin contacts); any other command is answered with the
guest message.

Commands are rare, so one extra `get_chat_member` call per command is
acceptable. Non-command messages pass through (the wizard router's own access
middleware handles wizard content).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import Message, TelegramObject

from bot.logging_setup import get_logger
from bot.services.access import AccessService, PublishChannel
from bot.services.access_messages import build_guest_message
from bot.services.membership import MembershipService

_log = get_logger("bot.guest_gate")

# guest-allowed commands: /start and /recheck show the guest message
# themselves; /post and /cancel are gated by the wizard router's middleware.
_ALLOWED_COMMANDS = {"/start", "/recheck", "/post", "/cancel"}


class GuestGateMiddleware(BaseMiddleware):
    def __init__(self, access: AccessService, membership: MembershipService) -> None:
        self._access = access
        self._membership = membership

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        if event.chat.type != ChatType.PRIVATE:
            return await handler(event, data)

        user = event.from_user
        if user is None:
            return await handler(event, data)

        text = event.text or ""
        if not text.startswith("/"):
            return await handler(event, data)  # non-command; other gates handle it

        command = text.split()[0].split("@")[0].lower()
        if command in _ALLOWED_COMMANDS:
            return await handler(event, data)

        decision = await self._access.resolve(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            channel=PublishChannel.PM,
        )
        if decision.is_staff:
            return await handler(event, data)
        if await self._membership.is_member(user.id):
            return await handler(event, data)

        _log.info("guest_command_blocked", user_id=user.id, command=command)
        session_factory = data["session_factory"]
        await event.answer(await build_guest_message(session_factory))
        return None
