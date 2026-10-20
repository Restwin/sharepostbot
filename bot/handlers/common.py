"""Common handlers: /start, /menu, /help, /version, inline-menu callbacks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, LinkPreviewOptions, Message, User
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import texts
from bot.config import Settings
from bot.db.models import UserRole
from bot.db.repo.chats import ChatRepository
from bot.db.repo.links import LinksRepository
from bot.db.repo.users import UserRepository
from bot.handlers.add_chat import start_add_chat
from bot.handlers.admin_users import (
    _render_admin_contacts_list,
    _render_categories_list,
    _render_stats_categories,
    _render_stats_recent,
    _render_stats_users,
    start_categories_add,
    start_categories_hide,
    start_categories_order,
    start_categories_remove,
    start_categories_show,
    start_users_block,
    start_users_set,
    start_users_unblock,
)
from bot.handlers.chat_manage import start_block_chat, start_remove_chat, start_unblock_chat
from bot.handlers.links import LinksState, render_links_text
from bot.handlers.posts import render_recent_posts, render_user_posts
from bot.menus import inline_menu
from bot.services.access import AccessDecision, AccessService, PublishChannel
from bot.services.access_messages import (
    blocked_pm_reply,
    build_admin_contacts_text,
    build_guest_message,
    collect_staff_ids,
    role_label_ru,
)
from bot.services.help_text import build_help
from bot.services.membership import MembershipService
from bot.utils.callbacks import MenuCallback
from bot.utils.formatting import html_escape
from bot.utils.replies import safe_answer, temp_reply
from bot.version import get_version

router = Router(name="common")

# private-chat text that is not a command; named so it can be unit-tested.
# aiogram stops at the first matching handler, so without the command check
# this fallback would swallow commands meant for later routers.
_PM_NON_COMMAND_TEXT = (F.chat.type == ChatType.PRIVATE) & F.text & ~F.text.startswith("/")


async def _resolve(user: User, access: AccessService) -> AccessDecision:
    return await access.resolve(
        user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        channel=PublishChannel.PM,
    )


async def _menu_keyboard(
    decision: AccessDecision,
    is_member: bool,
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
) -> InlineKeyboardMarkup | None:
    """Menu keyboard, or None for guests and blocked users (no menu)."""
    if decision.role == UserRole.BLOCKED:
        return None
    if not decision.is_staff and not is_member:
        return None
    async with session_factory() as session:
        links = await LinksRepository(session).get()
    return inline_menu.main_menu(
        is_staff=decision.is_staff,
        links=links,
        link_icon_custom_emoji_id=settings.link_icon_custom_emoji_id,
    )


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def cmd_start(
    message: Message,
    settings: Settings,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = message.from_user
    if user is None:
        return
    decision = await _resolve(user, access)
    is_member = True if decision.is_staff else await membership.is_member(user.id)
    if not is_member:
        await message.answer(
            await build_guest_message(session_factory),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return

    keyboard = None
    if message.chat.type == ChatType.PRIVATE:
        keyboard = await _menu_keyboard(decision, is_member, session_factory, settings)
    await message.answer(
        texts.START_GREETING.format(name=html_escape(user.first_name or "?")),
        reply_markup=keyboard,
    )


@router.message(Command("recheck"), F.chat.type == ChatType.PRIVATE)
async def cmd_recheck(
    message: Message,
    settings: Settings,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = message.from_user
    if user is None:
        return
    decision = await _resolve(user, access)
    is_member = True if decision.is_staff else await membership.is_member(user.id)
    if not is_member:
        await message.answer(
            await build_guest_message(session_factory),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return

    keyboard = None
    if message.chat.type == ChatType.PRIVATE:
        keyboard = await _menu_keyboard(decision, is_member, session_factory, settings)
    await message.answer(texts.RECHECK_OK, reply_markup=keyboard)


@router.message(Command("menu"), F.chat.type == ChatType.PRIVATE)
async def cmd_menu(
    message: Message,
    settings: Settings,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = message.from_user
    if user is None:
        return
    decision = await _resolve(user, access)
    is_member = True if decision.is_staff else await membership.is_member(user.id)
    keyboard = await _menu_keyboard(decision, is_member, session_factory, settings)
    if keyboard is None:
        await message.answer(texts.MENU_UNAVAILABLE_COMMANDS)
        return
    await message.answer(texts.MENU_TITLE, reply_markup=keyboard)


@router.message(Command("help"))
async def cmd_help(message: Message, settings: Settings, access: AccessService) -> None:
    user = message.from_user
    if user is None:
        return
    decision = await _resolve(user, access)
    is_staff = decision.is_staff and message.chat.type == ChatType.PRIVATE
    await message.answer(
        build_help(bot_name=settings.bot_name, is_staff=is_staff),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


@router.message(StateFilter(None), _PM_NON_COMMAND_TEXT)
async def pm_fallback(
    message: Message,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Catch-all for stray non-command text in PM with no active FSM state."""
    user = message.from_user
    if user is None:
        return
    decision = await _resolve(user, access)
    is_member = True if decision.is_staff else await membership.is_member(user.id)
    if not is_member:
        await message.answer(
            await build_guest_message(session_factory),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return
    await message.answer(
        texts.PM_FALLBACK,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )


@router.message(Command("version"), F.chat.type == ChatType.PRIVATE)
async def cmd_version(message: Message, access: AccessService) -> None:
    user = message.from_user
    if user is None:
        return
    if not (await _resolve(user, access)).is_staff:
        return
    await temp_reply(message, texts.VERSION_REPLY.format(version=get_version()))


# ── Menu action hints (arg-required / side-effecting commands) ────────────────
_HINTS: dict[str, str] = {
    "admin_contacts:add": texts.HINT_CONTACTS_ADD,
    "admin_contacts:remove": texts.HINT_CONTACTS_REMOVE,
    "admin_contacts:order": texts.HINT_CONTACTS_ORDER,
    "stats:user": texts.HINT_STATS_USER,
}


def _parse_page(sub: str) -> int:
    try:
        page = int(sub)
    except ValueError:
        return 1
    return max(1, page)


def _total_pages(total: int, size: int) -> int:
    return max(1, (total + size - 1) // size)


@dataclass(slots=True)
class _MenuCtx:
    message: Message
    decision: AccessDecision
    is_staff: bool
    is_member: bool


async def _menu_context(
    query: CallbackQuery,
    access: AccessService,
    membership: MembershipService,
) -> _MenuCtx | None:
    """Resolve the sender for a menu callback; None when the message is gone."""
    if query.message is None:
        await safe_answer(query, texts.CB_CANT_EDIT)
        return None
    decision = await _resolve(query.from_user, access)
    is_staff = decision.is_staff
    is_member = True if is_staff else await membership.is_member(query.from_user.id)
    return _MenuCtx(
        message=cast(Message, query.message),
        decision=decision,
        is_staff=is_staff,
        is_member=is_member,
    )


async def _member_gate(
    query: CallbackQuery,
    ctx: _MenuCtx,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    """True when a member-level action may proceed; else shows the guest message."""
    if not ctx.is_staff and not ctx.is_member:
        await ctx.message.answer(await build_guest_message(session_factory))
        await safe_answer(query)
        return False
    return True


async def _staff_gate(query: CallbackQuery, ctx: _MenuCtx) -> bool:
    """True when a STAFF-level action may proceed; else shows an alert."""
    if not ctx.is_staff:
        await safe_answer(query, texts.CB_ADMIN_ONLY, show_alert=True)
        return False
    return True


# ── Menu callbacks, one handler per action ────────────────────────────────────
# specific action filters must be registered before the generic catch-all below
# (aiogram dispatches to the first matching handler)


@router.callback_query(MenuCallback.filter(F.action == "link_missing"))
async def menu_link_missing(query: CallbackQuery) -> None:
    """Placeholder pressed for an unset community link."""
    await safe_answer(query, texts.CB_LINK_MISSING, show_alert=True)


@router.callback_query(MenuCallback.filter(F.action == "add_chat"))
async def menu_add_chat(
    query: CallbackQuery,
    state: FSMContext,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _member_gate(query, ctx, session_factory):
        return
    if ctx.decision.role == UserRole.BLOCKED:
        await ctx.message.answer(blocked_pm_reply(ctx.decision))
        await safe_answer(query)
        return
    await start_add_chat(state, ctx.message)
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "help"))
async def menu_help(
    query: CallbackQuery,
    settings: Settings,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _member_gate(query, ctx, session_factory):
        return
    await ctx.message.answer(
        build_help(bot_name=settings.bot_name, is_staff=ctx.is_staff),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "contacts"))
async def menu_contacts(
    query: CallbackQuery,
    settings: Settings,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _member_gate(query, ctx, session_factory):
        return
    if ctx.is_staff:
        staff_ids = await collect_staff_ids(settings, session_factory)
        async with session_factory() as session:
            all_users = {usr.id: usr for usr in await UserRepository(session).get_all()}
        lines = []
        for uid in sorted(staff_ids):
            usr = all_users.get(uid)
            handle = f"@{usr.username}" if usr and usr.username else f"id:{uid}"
            lines.append(f"• {html_escape(handle)}")
        text = texts.ADMINS_HEADER + ("\n".join(lines) if lines else texts.ADMINS_EMPTY)
        await ctx.message.edit_text(text, reply_markup=inline_menu.admin_contacts_menu())
    else:
        text, keyboard = await build_admin_contacts_text(session_factory)
        rows = keyboard.inline_keyboard if keyboard else []
        rows.append([inline_menu.back_button()])
        await ctx.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "my_chats"))
async def menu_my_chats(
    query: CallbackQuery,
    callback_data: MenuCallback,
    settings: Settings,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _member_gate(query, ctx, session_factory):
        return
    page = _parse_page(callback_data.sub)
    await _render_chats_page(
        ctx.message,
        query,
        page,
        settings.list_page_chats,
        session_factory,
        user_id=query.from_user.id,
        title=texts.MY_CHATS_TITLE,
        empty_text=texts.MY_CHATS_EMPTY,
        admin=False,
    )


@router.callback_query(MenuCallback.filter(F.action == "all_chats"))
async def menu_all_chats(
    query: CallbackQuery,
    callback_data: MenuCallback,
    settings: Settings,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    page = _parse_page(callback_data.sub)
    await _render_chats_page(
        ctx.message,
        query,
        page,
        settings.list_page_chats,
        session_factory,
        user_id=None,
        title=texts.ALL_CHATS_TITLE,
        empty_text=texts.ALL_CHATS_EMPTY,
        admin=True,
        show_blocked=True,
    )


@router.callback_query(MenuCallback.filter(F.action == "myposts"))
async def menu_myposts(
    query: CallbackQuery,
    settings: Settings,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _member_gate(query, ctx, session_factory):
        return
    await render_user_posts(
        ctx.message, session_factory, query.from_user.id, settings.main_channel_id
    )
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "back"))
async def menu_back(
    query: CallbackQuery,
    settings: Settings,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None:
        return
    keyboard = await _menu_keyboard(ctx.decision, ctx.is_member, session_factory, settings)
    if keyboard is None:
        await ctx.message.edit_text(texts.MENU_UNAVAILABLE)
        await safe_answer(query)
        return
    await ctx.message.edit_text(texts.MENU_TITLE, reply_markup=keyboard)
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "version"))
async def menu_version(
    query: CallbackQuery,
    access: AccessService,
    membership: MembershipService,
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    await ctx.message.answer(texts.VERSION_REPLY.format(version=get_version()))
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "chat_manage"))
async def menu_chat_manage(
    query: CallbackQuery,
    access: AccessService,
    membership: MembershipService,
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    await ctx.message.edit_text(
        texts.CHAT_MANAGE_TITLE, reply_markup=inline_menu.chat_manage_menu()
    )
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "users"))
async def menu_users(
    query: CallbackQuery,
    callback_data: MenuCallback,
    state: FSMContext,
    settings: Settings,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    sub = callback_data.sub
    if sub == "":
        await ctx.message.edit_text(texts.USERS_TITLE, reply_markup=inline_menu.users_menu())
        await safe_answer(query)
        return
    if sub in ("set", "block", "unblock"):
        starter = {
            "set": start_users_set,
            "block": start_users_block,
            "unblock": start_users_unblock,
        }[sub]
        await starter(ctx.message, state)
        await safe_answer(query)
        return
    # "list" (page 1) or a page number.
    await _render_users_page(
        ctx.message, query, _parse_page(sub), settings.list_page_users, session_factory
    )


@router.callback_query(MenuCallback.filter(F.action == "admin_contacts"))
async def menu_admin_contacts(
    query: CallbackQuery,
    callback_data: MenuCallback,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    lp = LinkPreviewOptions(is_disabled=True)
    sub = callback_data.sub
    if sub == "list":
        await ctx.message.answer(
            await _render_admin_contacts_list(session_factory), link_preview_options=lp
        )
    elif sub:
        await ctx.message.answer(_HINTS.get(f"admin_contacts:{sub}", _HINTS["admin_contacts:add"]))
    else:
        await ctx.message.edit_text(
            texts.CONTACTS_TITLE, reply_markup=inline_menu.admin_contacts_menu()
        )
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "categories"))
async def menu_categories(
    query: CallbackQuery,
    callback_data: MenuCallback,
    state: FSMContext,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    sub = callback_data.sub
    if sub == "":
        await ctx.message.edit_text(
            texts.CATEGORIES_TITLE, reply_markup=inline_menu.categories_menu()
        )
        await safe_answer(query)
        return
    starters = {
        "add": start_categories_add,
        "remove": start_categories_remove,
        "hide": start_categories_hide,
        "show": start_categories_show,
        "order": start_categories_order,
    }
    starter = starters.get(sub)
    if starter is not None:
        await starter(ctx.message, state, session_factory)
    else:
        await ctx.message.answer(
            await _render_categories_list(session_factory),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "stats"))
async def menu_stats(
    query: CallbackQuery,
    callback_data: MenuCallback,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    lp = LinkPreviewOptions(is_disabled=True)
    sub = callback_data.sub
    if sub == "recent":
        await ctx.message.answer(
            await _render_stats_recent(session_factory), link_preview_options=lp
        )
    elif sub == "categories":
        await ctx.message.answer(
            await _render_stats_categories(session_factory), link_preview_options=lp
        )
    elif sub == "users":
        await ctx.message.answer(
            await _render_stats_users(session_factory), link_preview_options=lp
        )
    elif sub == "user":
        await ctx.message.answer(_HINTS["stats:user"])
    else:
        await ctx.message.edit_text(texts.STATS_TITLE, reply_markup=inline_menu.stats_menu())
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "links"))
async def menu_links(
    query: CallbackQuery,
    access: AccessService,
    membership: MembershipService,
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    await ctx.message.edit_text(texts.LINKS_TITLE, reply_markup=inline_menu.links_menu())
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "links_show"))
async def menu_links_show(
    query: CallbackQuery,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    async with session_factory() as session:
        links = await LinksRepository(session).get()
    await ctx.message.answer(
        render_links_text(links), link_preview_options=LinkPreviewOptions(is_disabled=True)
    )
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "links_set"))
async def menu_links_set(
    query: CallbackQuery,
    callback_data: MenuCallback,
    state: FSMContext,
    access: AccessService,
    membership: MembershipService,
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    sub = callback_data.sub
    if sub not in ("rules", "channel", "chat"):
        await safe_answer(query, texts.CB_UNKNOWN_LINK, show_alert=True)
        return
    await state.set_state(LinksState.waiting_for_url)
    await state.update_data(link_key=sub)
    await ctx.message.answer(texts.LINKS_SET_PROMPT)
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "remove_chat"))
async def menu_remove_chat(
    query: CallbackQuery,
    state: FSMContext,
    access: AccessService,
    membership: MembershipService,
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    await start_remove_chat(ctx.message, state)
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "block_chat"))
async def menu_block_chat(
    query: CallbackQuery,
    state: FSMContext,
    access: AccessService,
    membership: MembershipService,
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    await start_block_chat(ctx.message, state)
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "unblock_chat"))
async def menu_unblock_chat(
    query: CallbackQuery,
    state: FSMContext,
    access: AccessService,
    membership: MembershipService,
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    await start_unblock_chat(ctx.message, state)
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "all_posts"))
async def menu_all_posts(
    query: CallbackQuery,
    settings: Settings,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    await render_recent_posts(
        ctx.message,
        session_factory,
        settings.main_channel_id,
        with_myposts_button=True,
    )
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "page_marker"))
async def menu_page_marker(query: CallbackQuery) -> None:
    """No-op handler for the middle pagination button."""
    await safe_answer(query)


@router.callback_query(MenuCallback.filter(F.action == "backup_db"))
async def menu_backup_db(
    query: CallbackQuery,
    settings: Settings,
    access: AccessService,
    membership: MembershipService,
) -> None:
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    if not settings.backup_to_chat_enabled:
        await ctx.message.edit_text(
            texts.BACKUP_DISABLED,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[inline_menu.back_button()]]),
        )
    else:
        await ctx.message.answer(texts.HINT_BACKUP_DB)
    await safe_answer(query)


@router.callback_query(MenuCallback.filter())
async def menu_action_hint(
    query: CallbackQuery,
    callback_data: MenuCallback,
    access: AccessService,
    membership: MembershipService,
) -> None:
    """Catch-all: side-effecting admin actions (remove_chat, block_chat, …)."""
    ctx = await _menu_context(query, access, membership)
    if ctx is None or not await _staff_gate(query, ctx):
        return
    if callback_data.action in _HINTS:
        await ctx.message.answer(_HINTS[callback_data.action])
    await safe_answer(query)


async def _render_chats_page(
    message: Message,
    query: CallbackQuery,
    page: int,
    size: int,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    user_id: int | None,
    title: str,
    empty_text: str,
    admin: bool,
    show_blocked: bool = False,
) -> None:
    """Render one page of chats (all chats for admins, own chats for members)."""
    async with session_factory() as session:
        repo = ChatRepository(session)
        total = await repo.count_by_added_by(user_id) if user_id is not None else await repo.count()
        pages = _total_pages(total, size)
        page = min(max(1, page), pages)
        offset = (page - 1) * size
        chats = (
            await repo.get_by_added_by_page(user_id, offset, size)
            if user_id is not None
            else await repo.get_page(offset, size)
        )

    if total == 0:
        await message.edit_text(
            empty_text, reply_markup=inline_menu.chats_page_menu(1, 1, admin=admin)
        )
        await safe_answer(query)
        return

    lines = []
    for c in chats:
        name = html_escape(c.exact_name)
        marker = texts.CHAT_ROW_BLOCKED_PREFIX if (show_blocked and c.is_blocked) else ""
        if c.join_link:
            link = html_escape(c.join_link)
            lines.append(
                marker + texts.CHAT_ROW_LINK.format(link=link, name=name, chat_id=c.chat_id)
            )
        else:
            lines.append(marker + texts.CHAT_ROW.format(name=name, chat_id=c.chat_id))

    blocks = [title]
    if pages > 1:
        blocks.append(
            texts.LIST_RANGE.format(start=offset + 1, end=min(offset + size, total), total=total)
        )
    await message.edit_text(
        "\n".join(blocks) + "\n\n" + "\n".join(lines),
        reply_markup=inline_menu.chats_page_menu(page, pages, admin=admin),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    await safe_answer(query)


async def _render_users_page(
    message: Message,
    query: CallbackQuery,
    page: int,
    size: int,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Render one page of users, most recently active first."""
    async with session_factory() as session:
        repo = UserRepository(session)
        total = await repo.count()
        pages = _total_pages(total, size)
        page = min(max(1, page), pages)
        users = await repo.get_page((page - 1) * size, size)

    if total == 0:
        await message.edit_text(
            texts.USERS_LIST_EMPTY, reply_markup=inline_menu.users_page_menu(1, 1)
        )
        await safe_answer(query)
        return

    lines = []
    for u in users:
        name = html_escape(
            " ".join(filter(None, [u.first_name, u.last_name])) or u.username or f"id:{u.id}"
        )
        handle = html_escape(f"@{u.username}") if u.username else "—"
        lines.append(
            f"• {name} ({handle}) <code>id:{u.id}</code> — "
            f"<b>{html_escape(role_label_ru(u.role))}</b>"
        )

    blocks = [texts.USERS_TITLE]
    if pages > 1:
        blocks.append(
            texts.LIST_RANGE.format(
                start=(page - 1) * size + 1, end=min(page * size, total), total=total
            )
        )
    await message.edit_text(
        "\n".join(blocks) + "\n\n" + "\n".join(lines),
        reply_markup=inline_menu.users_page_menu(page, pages),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
    await safe_answer(query)
