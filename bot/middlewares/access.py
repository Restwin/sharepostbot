"""Access middleware: gates publication by user role.

Installed on the `repost` router (mention in source chats) and the `wizard`
router (/post in PM). Also touches the user row on every relevant update, so
admin lists show current names and new users appear for vetting.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Router
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message, TelegramObject, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import texts
from bot.config import Settings
from bot.handlers.repost import is_repost_trigger
from bot.logging_setup import get_logger
from bot.services.access import AccessService, PublishChannel
from bot.services.access_messages import (
    blocked_mention_reply,
    blocked_pm_reply,
    build_guest_message,
    not_member_mention_reply,
)
from bot.services.membership import MembershipService
from bot.utils.replies import temp_reply

_log = get_logger("bot.access")


async def _publish_gate(
    access: AccessService,
    membership: MembershipService,
    user: User,
    channel: PublishChannel,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[Any, str | None]:
    """Resolve access and apply the role + membership gates.

    Returns `(decision, deny_reply)`: `deny_reply` is None when the user may
    proceed, otherwise the HTML text to show (block reason / guest message /
    not-a-member notice). The caller decides delivery (temp_reply in groups,
    plain reply in PM).
    """
    decision = await access.resolve(
        user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        channel=channel,
    )
    if not decision.allowed:
        if channel == PublishChannel.MENTION:
            return decision, blocked_mention_reply(decision)
        return decision, blocked_pm_reply(decision)
    # publishing is impossible while the bot is not in the main channel;
    # fail early with a clear message instead of a raw publish error
    if not await membership.bot_in_main_channel():
        return decision, texts.PUBLISH_BOT_NOT_IN_CHANNEL
    if not decision.is_staff and not await membership.is_member(user.id):
        if channel == PublishChannel.MENTION:
            return decision, not_member_mention_reply()
        return decision, await build_guest_message(session_factory)
    return decision, None


class RepostAccessMiddleware(BaseMiddleware):
    """Gate on the repost router: checks mention-posting rights."""

    def __init__(
        self,
        access: AccessService,
        membership: MembershipService,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
    ) -> None:
        self._access = access
        self._membership = membership
        self._session_factory = session_factory
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Message):
            return await handler(event, data)
        if event.chat.type == ChatType.PRIVATE:
            return await handler(event, data)

        # Only gate reply+mention posts; commands and other messages pass through.
        text = event.text or event.caption or ""
        if text.startswith("/"):
            return await handler(event, data)

        # same trigger detection as the repost handler; a cheap "@" check would
        # let trigger phrases bypass the gate for blocked users and non-members
        if not is_repost_trigger(
            event, self._settings.bot_name, self._settings.repost_trigger_phrases
        ):
            return await handler(event, data)

        user = event.from_user
        if user is None:
            return await handler(event, data)

        decision, deny = await _publish_gate(
            self._access,
            self._membership,
            user,
            PublishChannel.MENTION,
            self._session_factory,
        )
        data["access_decision"] = decision
        if deny is not None:
            _log.info(
                "access_denied_mention",
                user_id=user.id,
                role=int(decision.role),
                chat_id=event.chat.id,
            )
            await temp_reply(event, deny)
            return None
        return await handler(event, data)


class WizardAccessMiddleware(BaseMiddleware):
    """Gate on the wizard router: blocks BLOCKED/guest from starting /post."""

    def __init__(
        self,
        access: AccessService,
        membership: MembershipService,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._access = access
        self._membership = membership
        self._session_factory = session_factory

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message):
            return await self._gate_message(event, data, handler)
        if isinstance(event, CallbackQuery):
            return await self._gate_callback(event, data, handler)
        return await handler(event, data)

    async def _gate_message(
        self,
        event: Message,
        data: dict[str, Any],
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
    ) -> Any:
        user = event.from_user
        if user is None:
            return await handler(event, data)
        # Only gate private chat — group commands aren't wizard input.
        if event.chat.type != ChatType.PRIVATE:
            return await handler(event, data)
        text = event.text or ""

        # /cancel always allowed — lets a stuck user abort the wizard.
        if text.startswith("/cancel"):
            return await handler(event, data)

        # Gate /post and content-in-wizard-state (so a user who lost access
        # mid-session can't publish).
        if not text.startswith("/post"):
            state = data.get("state")
            if state is None:
                return await handler(event, data)
            current = await state.get_state()
            if current is None:
                return await handler(event, data)

        decision, deny = await _publish_gate(
            self._access,
            self._membership,
            user,
            PublishChannel.PM,
            self._session_factory,
        )
        data["access_decision"] = decision
        if deny is not None:
            _log.info(
                "access_denied_pm",
                user_id=user.id,
                role=int(decision.role),
            )
            await event.reply(deny)
            return None
        return await handler(event, data)

    async def _gate_callback(
        self,
        event: CallbackQuery,
        data: dict[str, Any],
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
    ) -> Any:
        # Publish/cancel callbacks: gate publish by access (cancel always ok).
        cb_data = data.get("callback_data")
        action = getattr(cb_data, "action", None)
        if action != "publish":
            return await handler(event, data)

        decision, deny = await _publish_gate(
            self._access,
            self._membership,
            event.from_user,
            PublishChannel.PM,
            self._session_factory,
        )
        data["access_decision"] = decision
        if deny is not None:
            _log.info(
                "access_denied_publish_callback",
                user_id=event.from_user.id,
                role=int(decision.role),
            )
            if event.message is not None:
                await event.message.reply(deny)
            return None
        return await handler(event, data)


def install_access_gates(
    repost_router: Router,
    wizard_router: Router,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> None:
    """Wire the two access middlewares onto their routers (inner scope)."""
    repost_router.message.middleware(
        RepostAccessMiddleware(access, membership, session_factory, settings)
    )
    wizard_router.message.middleware(WizardAccessMiddleware(access, membership, session_factory))
    wizard_router.callback_query.middleware(
        WizardAccessMiddleware(access, membership, session_factory)
    )
