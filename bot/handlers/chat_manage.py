"""Chat management commands: /get_all_chats, /remove_chat, /block_chat, /unblock_chat,
plus the FSM flows started from the inline menu (name-or-id + optional reason).

Chats are keyed by ChatId (immutable), so renaming never breaks a lookup. Both
the commands and the menu flows accept a chat by name or by id; a name that
matches several chats is ambiguous and must be refined by id.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ChatMemberAdministrator,
    ChatMemberUpdated,
    LinkPreviewOptions,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import texts
from bot.db.models import SavedChat
from bot.db.repo.chats import ChatRepository
from bot.logging_setup import get_logger
from bot.services.access import AccessService
from bot.services.access_messages import blocked_chat_lines, require_staff, resolve_user_handle
from bot.services.invite_links import create_confirm_link
from bot.utils.formatting import html_escape
from bot.utils.replies import notify_user, temp_reply

router = Router(name="chat_manage")
_log = get_logger("bot.chat_manage")


class ChatManageState(StatesGroup):
    """FSM: menu-driven remove/block/unblock of a chat by name or id."""

    waiting_for_target = State()
    waiting_for_reason = State()


def _is_chat_id(raw: str) -> bool:
    return bool(raw) and raw.lstrip("-").isdigit()


async def _resolve_chat_ref(repo: ChatRepository, raw: str) -> tuple[SavedChat | None, int]:
    """Resolve a name-or-id reference to a chat.

    Returns (chat, match_count): chat is set only when the reference is
    unambiguous; match_count 0 = not found, >1 = several chats with the name.
    """
    if _is_chat_id(raw):
        chat = await repo.get_by_chat_id(int(raw))
        return chat, 1 if chat is not None else 0
    matches = await repo.get_by_name_all(raw)
    if len(matches) == 1:
        return matches[0], 1
    return None, len(matches)


def _split_name_reason(raw: str) -> tuple[str, str]:
    """Split "<name> --- <reason>" into (name, reason); reason may be empty."""
    if "---" in raw:
        name, _, reason = raw.partition("---")
        return name.strip(), reason.strip()
    return raw.strip(), ""


def _can_invite(member: object) -> bool:
    return isinstance(member, ChatMemberAdministrator) and bool(member.can_invite_users)


# ── FSM entry points (called from the inline menu handlers) ──────────────────


async def start_remove_chat(message: Message, state: FSMContext) -> None:
    await state.set_state(ChatManageState.waiting_for_target)
    await state.update_data(action="remove")
    await message.answer(texts.CHAT_REMOVE_ASK)


async def start_block_chat(message: Message, state: FSMContext) -> None:
    await state.set_state(ChatManageState.waiting_for_target)
    await state.update_data(action="block")
    await message.answer(texts.CHAT_BLOCK_ASK)


async def start_unblock_chat(message: Message, state: FSMContext) -> None:
    await state.set_state(ChatManageState.waiting_for_target)
    await state.update_data(action="unblock")
    await message.answer(texts.CHAT_UNBLOCK_ASK)


def _cancel_on_command(state: FSMContext, text: str) -> bool:
    """True when the user typed a command while in a chat-manage state."""
    return text.startswith("/")


@router.message(ChatManageState.waiting_for_target, F.chat.type == ChatType.PRIVATE)
async def chat_target_input(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    raw = (message.text or "").strip()
    if _cancel_on_command(state, raw):
        await state.clear()
        await temp_reply(message, texts.CANCELLED)
        return

    action = (await state.get_data()).get("action")
    async with session_factory() as session:
        repo = ChatRepository(session)
        chat, matches = await _resolve_chat_ref(repo, raw)

        if matches == 0:
            await temp_reply(message, texts.CHAT_BLOCK_NOT_FOUND.format(name=html_escape(raw)))
            return
        if matches > 1:
            await temp_reply(message, texts.CHAT_AMBIGUOUS_NAME.format(name=html_escape(raw)))
            return
        assert chat is not None

        if action == "block":
            await state.update_data(chat_id=chat.chat_id)
            await state.set_state(ChatManageState.waiting_for_reason)
            await message.answer(texts.CHAT_BLOCK_ASK_REASON)
            return

        if action == "remove":
            name = chat.exact_name
            await session.delete(chat)
            await session.commit()
            await state.clear()
            await temp_reply(message, texts.CHAT_REMOVED.format(name=html_escape(name)))
            _log.info("chat_removed", chat_id=chat.chat_id, chat_name=name)
            return

        # action == "unblock"
        name = chat.exact_name
        chat.is_blocked = False
        chat.block_reason = ""
        chat.blocked_by = None
        owner_id = chat.added_by
        await session.commit()
        await state.clear()
        await temp_reply(message, texts.CHAT_UNBLOCKED.format(name=html_escape(name)))
        if owner_id is not None:
            await notify_user(
                bot,
                owner_id,
                texts.CHAT_UNBLOCKED_NOTIFY.format(name=html_escape(name)),
            )
        _log.info("chat_unblocked", chat_id=chat.chat_id, chat_name=name)


@router.message(ChatManageState.waiting_for_reason, F.chat.type == ChatType.PRIVATE)
async def chat_reason_input(
    message: Message,
    state: FSMContext,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    raw = (message.text or "").strip()
    if _cancel_on_command(state, raw):
        await state.clear()
        await temp_reply(message, texts.CANCELLED)
        return

    reason = "" if raw == "-" else raw
    data = await state.get_data()
    chat_id = data.get("chat_id")
    async with session_factory() as session:
        repo = ChatRepository(session)
        chat = await repo.get_by_chat_id(int(chat_id)) if isinstance(chat_id, int) else None
        if chat is None:
            await state.clear()
            await temp_reply(message, texts.CHAT_BLOCK_NOT_FOUND.format(name=str(chat_id)))
            return
        chat.is_blocked = True
        chat.block_reason = reason
        chat.blocked_by = message.from_user.id if message.from_user else None
        owner_id = chat.added_by
        name = chat.exact_name
        await session.commit()

    await state.clear()
    extra = texts.CHAT_BLOCK_REASON_PREFIX.format(reason=html_escape(reason)) if reason else ""
    await temp_reply(message, texts.CHAT_BLOCKED.format(name=html_escape(name), reason=extra))
    if owner_id is not None:
        await notify_user(
            bot,
            owner_id,
            texts.CHAT_BLOCKED_NOTIFY.format(name=html_escape(name)),
        )
    _log.info(
        "chat_blocked",
        chat_id=chat_id,
        chat_name=name,
        by=message.from_user.id if message.from_user else 0,
    )


@router.my_chat_member()
async def on_my_chat_member(
    update: ChatMemberUpdated,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """React to the bot's status change in a chat.

    Three cases:
    - Removed from the chat (left/kicked): drop the chat from the list (unless
      it's blocked) and notify the registrar.
    - Lost `can_invite_users` (demoted, still a member): clear the stale link
      and notify the owner.
    - Gained `can_invite_users` (promoted): (re-)export the invite link.
    """
    new_status = update.new_chat_member.status
    chat_id = update.chat.id

    # ─── Bot removed from the chat entirely ───
    if new_status in ("left", "kicked"):
        async with session_factory() as session:
            repo = ChatRepository(session)
            saved = await repo.get_by_chat_id(chat_id)
            if saved is None:
                return
            owner_id = saved.added_by
            chat_name = saved.exact_name or update.chat.title or str(chat_id)
            blocked = saved.is_blocked
            if not blocked:
                await session.delete(saved)
            await session.commit()

        _log.info(
            "bot_removed",
            chat_id=chat_id,
            chat_name=chat_name,
            blocked=blocked,
        )
        if owner_id is not None:
            text = texts.CHAT_BOT_REMOVED_BLOCKED if blocked else texts.CHAT_BOT_REMOVED
            try:
                await bot.send_message(owner_id, text.format(name=html_escape(chat_name)))
            except TelegramBadRequest as exc:
                _log.warning("bot_removed_notify_failed", owner_id=owner_id, error=str(exc))
        return

    # ─── Invite-right change (still a member) ───
    had_invite = _can_invite(update.old_chat_member)
    has_invite = _can_invite(update.new_chat_member)
    if had_invite == has_invite:
        return  # no change in the invite-link right

    if not has_invite:
        # Demotion: clear the bot-exported link + notify. A permanent PM link stays.
        async with session_factory() as session:
            repo = ChatRepository(session)
            saved = await repo.get_by_chat_id(chat_id)
            if saved is None or saved.added_by is None:
                return
            if saved.link_source == "pm":
                return  # permanent link, unaffected by losing admin
            owner_id = saved.added_by
            chat_name = saved.exact_name or update.chat.title or str(chat_id)
            saved.join_link = ""
            await session.commit()

        _log.info("admin_lost", chat_id=chat_id, chat_name=chat_name, owner_id=owner_id)
        try:
            await bot.send_message(
                owner_id, texts.CHAT_ADMIN_LOST.format(name=html_escape(chat_name))
            )
        except TelegramBadRequest as exc:
            _log.warning("admin_lost_notify_failed", owner_id=owner_id, error=str(exc))
        return

    # Promotion: (re-)create the invite link, unless a permanent PM link exists.
    async with session_factory() as session:
        repo = ChatRepository(session)
        saved = await repo.get_by_chat_id(chat_id)
        if saved is not None and saved.link_source == "pm":
            return  # permanent link, keep it, don't overwrite

    # Keep the link type the owner chose: "confirm" links are recreated as
    # join-request links; everything else uses the chat's primary link.
    approval = (saved.join_approval or "open") if saved is not None else "open"
    try:
        if approval == "confirm":
            join_link = await create_confirm_link(bot, chat_id)
        else:
            join_link = await bot.export_chat_invite_link(chat_id)
    except TelegramBadRequest as exc:
        _log.warning("regain_export_failed", chat_id=chat_id, error=str(exc))
        return

    is_new = False
    async with session_factory() as session:
        repo = ChatRepository(session)
        saved = await repo.get_by_chat_id(chat_id)
        if saved is None:
            await repo.add_or_update(
                chat_id=chat_id,
                exact_name=update.chat.title or str(chat_id),
                join_link=join_link,
                added_by=update.from_user.id if update.from_user else None,
                link_source="bot",
                join_approval=approval,
            )
            is_new = True
        else:
            saved.join_link = join_link
            saved.link_source = "bot"
            saved.join_approval = approval
            if update.chat.title:
                saved.exact_name = update.chat.title
        await session.commit()

    _log.info("admin_regained", chat_id=chat_id, chat_name=update.chat.title)
    if is_new and update.from_user is not None:
        await notify_user(
            bot,
            update.from_user.id,
            texts.CHAT_REGISTERED_NOTIFY.format(
                name=html_escape(update.chat.title or str(chat_id))
            ),
        )


@router.message(F.new_chat_title, F.chat.type != ChatType.PRIVATE)
async def on_chat_title_changed(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Service message: group/supergroup was renamed.

    Updates SavedChat.exact_name immediately. This is the reliable rename signal
    (an explicit Telegram event); ChatLookupService.resolve() only catches
    renames through message.chat.title drift when the service message never
    arrived.
    """
    new_title = message.new_chat_title
    if not new_title:
        return

    chat_id = message.chat.id
    async with session_factory() as session:
        repo = ChatRepository(session)
        saved = await repo.get_by_chat_id(chat_id)
        if saved is None:
            return  # untracked chat, nothing to update
        if saved.exact_name == new_title:
            return
        _log.info(
            "chat_renamed_service_msg",
            chat_id=chat_id,
            old_name=saved.exact_name,
            new_name=new_title,
            message_id=message.message_id,
        )
        saved.exact_name = new_title
        await session.commit()


@router.message(F.migrate_to_chat_id, F.chat.type != ChatType.PRIVATE)
async def on_chat_migrated(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Service message: group migrated to supergroup; SavedChat.chat_id is updated."""
    new_id_raw = message.migrate_to_chat_id
    if new_id_raw is None:
        return
    new_id: int = new_id_raw
    old_id = message.chat.id
    async with session_factory() as session:
        repo = ChatRepository(session)
        saved = await repo.get_by_chat_id(old_id)
        if saved is None:
            return
        _log.info(
            "chat_migrated_service_msg",
            old_chat_id=old_id,
            new_chat_id=new_id,
            chat_name=saved.exact_name,
            message_id=message.message_id,
        )
        saved.chat_id = new_id
        await session.commit()


@router.message(Command("get_all_chats"), F.chat.type == ChatType.PRIVATE)
async def get_all_chats(
    message: Message,
    access: AccessService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not await require_staff(message, access):
        return

    async with session_factory() as session:
        repo = ChatRepository(session)
        chats = await repo.get_all()

    if not chats:
        await temp_reply(message, texts.CHAT_LIST_EMPTY)
        return

    lines = []
    for c in chats:
        name = html_escape(c.exact_name)
        marker = texts.CHAT_ROW_BLOCKED_PREFIX if c.is_blocked else ""
        who = (
            html_escape(await resolve_user_handle(session_factory, c.added_by))
            if c.added_by is not None
            else texts.CHAT_ADDED_BY_UNKNOWN
        )
        if c.join_link:
            link = html_escape(c.join_link)
            lines.append(
                texts.CHAT_LIST_LINE_LINK.format(
                    marker=marker, link=link, name=name, who=who, chat_id=c.chat_id
                )
            )
        else:
            lines.append(
                texts.CHAT_LIST_LINE_NO_LINK.format(
                    marker=marker, name=name, who=who, chat_id=c.chat_id
                )
            )
        if c.is_blocked:
            lines[-1] += "\n" + "\n".join(
                await blocked_chat_lines(
                    session_factory, block_reason=c.block_reason, blocked_by=c.blocked_by
                )
            )
    await message.reply(
        "\n\n".join(lines), link_preview_options=LinkPreviewOptions(is_disabled=True)
    )


@router.message(Command("remove_chat"), F.chat.type == ChatType.PRIVATE)
async def remove_chat(
    message: Message,
    access: AccessService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not await require_staff(message, access):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await temp_reply(message, texts.CHAT_REMOVE_EXAMPLE)
        return

    ref = parts[1].strip()
    async with session_factory() as session:
        repo = ChatRepository(session)
        chat, matches = await _resolve_chat_ref(repo, ref)
        if matches == 0:
            await temp_reply(message, texts.CHAT_REMOVE_NOT_FOUND.format(name=html_escape(ref)))
            return
        if matches > 1:
            await temp_reply(message, texts.CHAT_AMBIGUOUS_NAME.format(name=html_escape(ref)))
            return
        assert chat is not None
        name = chat.exact_name
        await repo.remove_by_chat_id(chat.chat_id)
        await session.commit()

    await temp_reply(message, texts.CHAT_REMOVED.format(name=html_escape(name)))
    _log.info("chat_removed", chat_id=chat.chat_id, chat_name=name)


@router.message(Command("block_chat"), F.chat.type == ChatType.PRIVATE)
async def block_chat(
    message: Message,
    bot: Bot,
    access: AccessService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not await require_staff(message, access):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await temp_reply(message, texts.CHAT_BLOCK_EXAMPLE)
        return

    ref, reason = _split_name_reason(parts[1])
    admin_id = message.from_user.id if message.from_user else None
    async with session_factory() as session:
        repo = ChatRepository(session)
        chat, matches = await _resolve_chat_ref(repo, ref)
        if matches == 0:
            await temp_reply(message, texts.CHAT_BLOCK_NOT_FOUND.format(name=html_escape(ref)))
            return
        if matches > 1:
            await temp_reply(message, texts.CHAT_AMBIGUOUS_NAME.format(name=html_escape(ref)))
            return
        assert chat is not None
        chat.is_blocked = True
        chat.block_reason = reason
        chat.blocked_by = admin_id
        name = chat.exact_name
        owner_id = chat.added_by
        await session.commit()

    extra = texts.CHAT_BLOCK_REASON_PREFIX.format(reason=html_escape(reason)) if reason else ""
    await temp_reply(message, texts.CHAT_BLOCKED.format(name=html_escape(name), reason=extra))
    if owner_id is not None:
        await notify_user(
            bot,
            owner_id,
            texts.CHAT_BLOCKED_NOTIFY.format(name=html_escape(name)),
        )


@router.message(Command("unblock_chat"), F.chat.type == ChatType.PRIVATE)
async def unblock_chat(
    message: Message,
    bot: Bot,
    access: AccessService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not await require_staff(message, access):
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await temp_reply(message, texts.CHAT_UNBLOCK_EXAMPLE)
        return

    ref = parts[1].strip()
    async with session_factory() as session:
        repo = ChatRepository(session)
        chat, matches = await _resolve_chat_ref(repo, ref)
        if matches == 0:
            await temp_reply(message, texts.CHAT_BLOCK_NOT_FOUND.format(name=html_escape(ref)))
            return
        if matches > 1:
            await temp_reply(message, texts.CHAT_AMBIGUOUS_NAME.format(name=html_escape(ref)))
            return
        assert chat is not None
        chat.is_blocked = False
        chat.block_reason = ""
        chat.blocked_by = None
        name = chat.exact_name
        owner_id = chat.added_by
        await session.commit()

    await temp_reply(message, texts.CHAT_UNBLOCKED.format(name=html_escape(name)))
    if owner_id is not None:
        await notify_user(
            bot,
            owner_id,
            texts.CHAT_UNBLOCKED_NOTIFY.format(name=html_escape(name)),
        )
