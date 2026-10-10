"""Channel membership check: gates publishing to community members only.

The bot posts to `Settings.main_channel_id`; users who found the bot but are
not in that channel should not publish (or see posting UI). STAFF bypass the
check at the call site (admins are not necessarily channel members).

Fail-open: on an API error (e.g. transient network) `is_member` returns True
and logs, so a temporary outage never locks out the whole community.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.utils.chat_member import MEMBERS

from bot.config import Settings
from bot.logging_setup import get_logger

_log = get_logger("bot.membership")


class MembershipService:
    def __init__(self, bot: Bot, settings: Settings) -> None:
        self._bot = bot
        self._settings = settings

    async def is_member(self, user_id: int) -> bool:
        """True if the user is a member of the main channel (not left/kicked)."""
        try:
            member = await self._bot.get_chat_member(self._settings.main_channel_id, user_id)
        except Exception as exc:  # fail-open
            _log.warning("membership_check_failed", user_id=user_id, error=str(exc))
            return True
        return isinstance(member, MEMBERS)
