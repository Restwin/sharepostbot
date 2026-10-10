"""Creating the two invite-link types used during registration.

- "open": secondary named link without join requests; falls back to the chat's
  primary invite link (exportChatInviteLink), which needs no approval by
  itself (group settings may still require it).
- "confirm": secondary named link with join requests (admins approve new
  members). Supergroups/channels only: a basic group rejects it with a
  "supergroups" hint in the error message.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest

from bot import texts
from bot.logging_setup import get_logger

_log = get_logger("bot.invite_links")


async def create_open_link(bot: Bot, chat_id: int) -> str:
    try:
        link = await bot.create_chat_invite_link(
            chat_id,
            name=texts.ONBOARDING_LINK_NAME_OPEN,
            creates_join_request=False,
        )
        return link.invite_link
    except TelegramBadRequest as exc:
        _log.info("open_link_fallback_to_primary", chat_id=chat_id, error=str(exc))
        return await bot.export_chat_invite_link(chat_id)


async def create_confirm_link(bot: Bot, chat_id: int) -> str:
    link = await bot.create_chat_invite_link(
        chat_id,
        name=texts.ONBOARDING_LINK_NAME_CONFIRM,
        creates_join_request=True,
    )
    return link.invite_link
