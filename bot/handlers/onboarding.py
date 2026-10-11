"""Onboarding: when the bot is added to a new group, send instructions and
inline buttons for the inviter to register the chat.

Actions:
  - "admin_confirm": bot is admin with can_invite_users; create a named invite
    link with join requests (new members must be approved by admins).
  - "admin_open": same rights; create a named invite link without approval.
  - "admin": alias for "admin_open" (older in-flight keyboards may send it).
  - "member": add to the DB without an invite link; the signature then shows
    the chat title but no clickable link.
  - "leave": bot leaves the chat.

Only the user who added the bot can press the buttons. chat_id and title come
from the new_chat_members service message.

"Источник" links: Telegram supports direct message links only for supergroups
and channels (chat_id starts with -100). For basic groups the signature shows
the chat link if registered, but no per-message link.

Link types: join-request links ("с подтверждением") exist only for
supergroups/channels; in a basic group the button fails with a hint to convert
the group. Both types can coexist in one chat, but the bot stores one link per
chat (the one used in post signatures), so the button pressed decides which
link is kept.
"""

from __future__ import annotations

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Filter
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMemberAdministrator,
    LinkPreviewOptions,
    Message,
    User,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import texts
from bot.config import Settings
from bot.db.repo.chats import ChatRepository
from bot.logging_setup import get_logger
from bot.services.access_messages import blocked_chat_lines
from bot.services.invite_links import create_confirm_link, create_open_link
from bot.utils.callbacks import OnboardingCallback
from bot.utils.formatting import html_escape
from bot.utils.replies import notify_user, safe_answer, send_long_answer

router = Router(name="onboarding")
_log = get_logger("bot.onboarding")


def _onboarding_text(bot_name: str, *, registered: bool = False) -> str:
    """Common intro + a tail that depends on whether the chat is registered."""
    tail = texts.ONBOARDING_ALREADY_REGISTERED if registered else texts.ONBOARDING_NOT_REGISTERED
    return texts.ONBOARDING_TEXT.format(bot_name=bot_name) + tail


def _already_registered_text(bot_name: str) -> str:
    return _onboarding_text(bot_name, registered=True)


async def _bot_has_invite(bot: Bot, chat_id: int) -> bool:
    """True when the bot is an admin with the invite-links right in `chat_id`."""
    try:
        me = await bot.get_chat_member(chat_id, bot.id)
    except TelegramBadRequest:
        return False
    return isinstance(me, ChatMemberAdministrator) and bool(me.can_invite_users)


async def _auto_register_if_admin(
    bot: Bot,
    message: Message,
    chat: Chat,
    inviter: User,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    """Auto-register when the bot already has invite rights at add time.

    The my_chat_member update races with the new_chat_members service message,
    so registering here makes the outcome deterministic: an "open" link is
    stored, the inviter is notified once, and the onboarding message is
    replaced. On failure the regular onboarding buttons stay.
    """
    if not await _bot_has_invite(bot, chat.id):
        return False
    try:
        join_link = await bot.export_chat_invite_link(chat.id)
    except TelegramBadRequest as exc:
        _log.warning(
            "auto_register_export_failed", chat_id=chat.id, error=str(exc), to_tech="business"
        )
        return False

    title = chat.title or str(chat.id)
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(
            chat_id=chat.id,
            exact_name=title,
            join_link=join_link,
            added_by=inviter.id,
            link_source="bot",
            join_approval="open",
        )
        await session.commit()

    _log.info("auto_registered", chat_id=chat.id, title=title)
    await notify_user(
        bot,
        inviter.id,
        texts.CHAT_REGISTERED_NOTIFY.format(name=html_escape(title)),
    )
    try:
        await message.reply(
            texts.ONBOARDING_ADMIN_DONE,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except TelegramBadRequest as exc:
        _log.error("onboarding_send_failed", chat_id=chat.id, error=str(exc))
    return True


class BotInNewMembers(Filter):
    """Filter: matches only when the bot itself is among new_chat_members."""

    async def __call__(self, message: Message, bot: Bot) -> bool:
        if not message.new_chat_members:
            return False
        return any(m.id == bot.id for m in message.new_chat_members)


@router.message(BotInNewMembers())
async def on_bot_added(
    message: Message,
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Bot added to a chat: register it and/or send onboarding buttons."""
    inviter = message.from_user
    if inviter is None:
        return

    chat = message.chat
    _log.info(
        "bot_added_to_chat",
        chat_id=chat.id,
        chat_title=chat.title,
        chat_type=chat.type,
        inviter_id=inviter.id,
        inviter_username=inviter.username,
    )

    async with session_factory() as session:
        repo = ChatRepository(session)
        existing = await repo.get_by_chat_id(chat.id)

    if existing is not None and existing.is_blocked:
        _log.info("bot_added_blocked_chat", chat_id=chat.id, title=chat.title, to_tech="business")
        lines = [texts.ONBOARDING_BLOCKED_CHAT]
        lines += await blocked_chat_lines(
            session_factory,
            block_reason=existing.block_reason,
            blocked_by=existing.blocked_by,
        )
        lines.append(texts.ONBOARDING_BLOCKED_HINT)
        try:
            await message.reply(
                "\n".join(lines),
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except TelegramBadRequest as exc:
            _log.error("onboarding_send_failed", chat_id=chat.id, error=str(exc))
        return

    # already registered and linked: nothing to do.
    if existing is not None and existing.join_link:
        _log.info("bot_added_already_registered", chat_id=chat.id, title=chat.title)
        try:
            await message.reply(
                _already_registered_text(settings.bot_name),
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except TelegramBadRequest as exc:
            _log.error("onboarding_send_failed", chat_id=chat.id, error=str(exc))
        return

    # re-added chat without a link: fall through to the onboarding buttons.
    if existing is not None:
        _log.info("bot_readded_without_link", chat_id=chat.id, title=chat.title)

    # bot already has invite rights: register now, no button press needed.
    if await _auto_register_if_admin(bot, message, chat, inviter, session_factory):
        return

    await _send_onboarding(message, chat, inviter, settings)


async def _send_onboarding(
    message: Message,
    chat: Chat,
    inviter: User,
    settings: Settings,
) -> None:
    builder = InlineKeyboardBuilder()
    builder.button(
        text=texts.ONBOARDING_BTN_ADMIN_CONFIRM,
        callback_data=OnboardingCallback(
            action="admin_confirm", chat_id=chat.id, inviter_id=inviter.id
        ),
    )
    builder.button(
        text=texts.ONBOARDING_BTN_ADMIN_OPEN,
        callback_data=OnboardingCallback(
            action="admin_open", chat_id=chat.id, inviter_id=inviter.id
        ),
    )
    builder.button(
        text=texts.ONBOARDING_BTN_MEMBER,
        callback_data=OnboardingCallback(action="member", chat_id=chat.id, inviter_id=inviter.id),
    )
    builder.button(
        text=texts.ONBOARDING_BTN_LEAVE,
        callback_data=OnboardingCallback(action="leave", chat_id=chat.id, inviter_id=inviter.id),
    )
    builder.adjust(1)

    try:
        await message.reply(
            _onboarding_text(settings.bot_name),
            reply_markup=builder.as_markup(),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    except TelegramBadRequest as exc:
        _log.error("onboarding_send_failed", chat_id=chat.id, error=str(exc))


@router.callback_query(OnboardingCallback.filter())
async def onboarding_callback(
    query: CallbackQuery,
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    callback_data: OnboardingCallback,
) -> None:
    action = callback_data.action
    chat_id = callback_data.chat_id
    inviter_id = callback_data.inviter_id

    # Only the inviter can press buttons.
    if query.from_user.id != inviter_id:
        await safe_answer(query, texts.ONBOARDING_NOT_INVITER, show_alert=True)
        return

    # leave
    if action == "leave":
        await safe_answer(query, texts.ONBOARDING_LEAVE_ACK)
        # edit before leaving: edit_text fails with Forbidden once the bot is gone
        if isinstance(query.message, Message):
            try:
                await query.message.edit_text(
                    texts.ONBOARDING_LEAVE_DONE,
                    reply_markup=None,
                )
            except TelegramBadRequest as exc:
                _log.warning("leave_edit_text_failed", chat_id=chat_id, error=str(exc))
        try:
            await bot.leave_chat(chat_id)
        except TelegramBadRequest as exc:
            _log.error("leave_chat_failed", chat_id=chat_id, error=str(exc))
            return
        _log.info("bot_left_chat", chat_id=chat_id, inviter_id=inviter_id)
        return

    # admin or member: register the chat in the DB
    try:
        chat = await bot.get_chat(chat_id)
    except TelegramBadRequest as exc:
        _log.error("get_chat_failed", chat_id=chat_id, error=str(exc))
        await safe_answer(query, texts.ONBOARDING_GET_CHAT_FAILED, show_alert=True)
        return

    title = chat.title or str(chat_id)
    join_link = ""
    join_approval = ""
    is_admin_path = action in ("admin", "admin_confirm", "admin_open")
    requested = "confirm" if action == "admin_confirm" else "open"

    if is_admin_path:
        # already has the requested link type, or any PM link: show
        # instructions only, no re-registration or notification.
        async with session_factory() as session:
            existing = await ChatRepository(session).get_by_chat_id(chat_id)
        if existing is not None and existing.join_link:
            stored = existing.join_approval or "open"
            if existing.link_source == "pm" or stored == requested:
                msg = texts.ONBOARDING_ADMIN_DONE
                if existing.link_source != "pm":
                    msg = (
                        texts.ONBOARDING_LINK_CONFIRM_DONE
                        if requested == "confirm"
                        else texts.ONBOARDING_LINK_OPEN_DONE
                    )
                await safe_answer(query)
                if isinstance(query.message, Message):
                    try:
                        await query.message.edit_text(
                            msg,
                            reply_markup=None,
                            link_preview_options=LinkPreviewOptions(is_disabled=True),
                        )
                    except TelegramBadRequest as exc:
                        _log.warning("onboarding_edit_text_failed", chat_id=chat_id, error=str(exc))
                return

        try:
            me_member = await bot.get_chat_member(chat_id, bot.id)
        except TelegramBadRequest as exc:
            _log.error("get_chat_member_failed", chat_id=chat_id, error=str(exc))
            await safe_answer(
                query,
                texts.ONBOARDING_GET_MEMBER_FAILED,
                show_alert=True,
            )
            return

        if not isinstance(me_member, ChatMemberAdministrator) or not me_member.can_invite_users:
            await send_long_answer(query, texts.ONBOARDING_NEED_ADMIN_RIGHTS, ttl=30)
            return

        try:
            if action == "admin_confirm":
                join_link = await create_confirm_link(bot, chat_id)
            else:
                join_link = await create_open_link(bot, chat_id)
        except TelegramBadRequest as exc:
            _log.error("create_invite_failed", chat_id=chat_id, error=str(exc))
            if "supergroup" in str(exc.message).lower():
                await send_long_answer(query, texts.ONBOARDING_NEED_SUPERGROUP, ttl=30)
            else:
                await send_long_answer(query, texts.ONBOARDING_EXPORT_FAILED, ttl=30)
            return
        join_approval = requested

    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(
            chat_id=chat_id,
            exact_name=title,
            join_link=join_link,
            added_by=inviter_id,
            link_source="bot",
            join_approval=join_approval,
        )
        await session.commit()

    _log.info(
        "chat_registered",
        chat_id=chat_id,
        title=title,
        has_link=bool(join_link),
        mode=action,
    )

    await safe_answer(query)
    if action == "admin_confirm":
        msg = texts.ONBOARDING_LINK_CONFIRM_DONE
        notify_text = texts.CHAT_REGISTERED_NOTIFY.format(name=html_escape(title))
    elif is_admin_path:
        msg = texts.ONBOARDING_LINK_OPEN_DONE
        notify_text = texts.CHAT_REGISTERED_NOTIFY.format(name=html_escape(title))
    else:
        msg = texts.ONBOARDING_MEMBER_DONE_CHAT
        # the detailed "how to add a permanent link" instructions go to PM.
        notify_text = texts.ONBOARDING_MEMBER_DONE_PM.format(
            name=html_escape(title), chat_id=chat_id
        )
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(
                msg, reply_markup=None, link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        except TelegramBadRequest as exc:
            _log.warning("onboarding_edit_text_failed", chat_id=chat_id, error=str(exc))
    await notify_user(bot, inviter_id, notify_text)
