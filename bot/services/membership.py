"""Channel membership check: gates publishing to community members only.

The bot posts to `Settings.main_channel_id`; users who found the bot but are
not in that channel should not publish (or see posting UI). STAFF bypass the
membership check at the call site (admins are not necessarily channel
members), but the channel itself must always be reachable — see
`bot_in_main_channel`.

Fail-open only on transient network errors: an outage never locks out the
whole community. A 400-class error (wrong MAIN_CHANNEL_ID, bot not in the
channel) fails closed — misconfiguration must not silently disable the gate.
"""

from __future__ import annotations

import time

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramServerError,
)
from aiogram.utils.chat_member import MEMBERS

from bot.config import Settings
from bot.logging_setup import get_logger

_log = get_logger("bot.membership")

_CHANNEL_OK_TTL = 60.0


class MembershipService:
    def __init__(self, bot: Bot, settings: Settings) -> None:
        self._bot = bot
        self._settings = settings
        self._channel_ok_at = 0.0
        self._channel_ok = True

    async def is_member(self, user_id: int) -> bool:
        """True if the user is a member of the main channel (not left/kicked)."""
        try:
            member = await self._bot.get_chat_member(self._settings.main_channel_id, user_id)
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            # bad chat id, or the bot lost access to the channel: treat as not
            # a member, otherwise a misconfigured deploy silently opens publishing
            _log.error("membership_check_failed_config", user_id=user_id, error=str(exc))
            return False
        except (TelegramNetworkError, TelegramServerError) as exc:
            _log.warning("membership_check_failed_network", user_id=user_id, error=str(exc))
            return True
        except Exception as exc:
            _log.warning("membership_check_failed", user_id=user_id, error=str(exc))
            return True
        return isinstance(member, MEMBERS)

    async def bot_in_main_channel(self) -> bool:
        """True when the bot can see the main channel (get_chat succeeds).

        Cached for 60s so every gated update does not add an API call.
        Fail-open on network errors; fail-closed on TelegramBadRequest /
        TelegramForbiddenError (bot removed from the channel, or a wrong
        MAIN_CHANNEL_ID). Publishing is blocked while this returns False.
        Losing access logs an error (forwarded to the tech chat); regaining
        it logs a system event.
        """
        now = time.monotonic()
        if now - self._channel_ok_at < _CHANNEL_OK_TTL:
            return self._channel_ok
        failure: str | None = None
        try:
            await self._bot.get_chat(self._settings.main_channel_id)
            ok = True
        except (TelegramBadRequest, TelegramForbiddenError) as exc:
            failure = str(exc)
            ok = False
        except (TelegramNetworkError, TelegramServerError) as exc:
            _log.warning("channel_check_failed_network", error=str(exc))
            ok = True
        except Exception as exc:
            _log.warning("channel_check_failed", error=str(exc))
            ok = True

        self._update_channel_state(ok, failure)
        return ok

    def set_main_channel_state(self, ok: bool, *, reason: str = "") -> None:
        """Update the cached channel state from an external signal.

        Used by the my_chat_member handler: the bot is removed from / added
        back to the main channel. Logs the transition (error → tech chat,
        recovery → system event) and refreshes the cache timestamp.
        """
        self._update_channel_state(ok, reason or None)

    def _update_channel_state(self, ok: bool, failure: str | None) -> None:
        if ok == self._channel_ok:
            self._channel_ok_at = time.monotonic()
            return
        if ok:
            _log.info("bot_back_in_main_channel", to_tech="system")
        else:
            _log.error(
                "bot_not_in_main_channel",
                chat_id=self._settings.main_channel_id,
                error=failure,
            )
        self._channel_ok = ok
        self._channel_ok_at = time.monotonic()
