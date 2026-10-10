"""Admin commands for managing users and the admin contact directory.

All commands require STAFF role (env ADMIN_IDS bootstrap OR DB role=STAFF).
The access check is done via `AccessService` so the same gate applies in PM
and in source chats.

User management:
  /users list                 — list all known users with their role
  /users set <id> allow|blocked|staff [reason...]
  /users set <id> unknown     — reset to UNKNOWN
  /users block <id> [reason] [pm|mention|both]   — shorthand for set blocked
  /users unblock <id>         — shorthand for set allow

Contact directory (shown to everyone via /contacts):
  /admin_contacts add <user_id> <role> [comment]
  /admin_contacts remove <user_id>
  /admin_contacts list
  /admin_contacts order <user_id> <int>
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import texts
from bot.db.models import PublishedPost, RestrictMode, UserRole
from bot.db.repo.categories import CategoryRepository
from bot.db.repo.contacts import AdminContactRepository
from bot.db.repo.stats import PostStatRepository
from bot.db.repo.users import UserRepository
from bot.logging_setup import get_logger
from bot.services.access import AccessService
from bot.services.access_messages import require_staff, role_label_ru
from bot.utils.callbacks import RolePickCallback
from bot.utils.formatting import html_escape
from bot.utils.replies import safe_answer, temp_reply

router = Router(name="admin_users")
_log = get_logger("bot.admin_users")

_ROLE_BY_NAME = {
    "unknown": UserRole.UNKNOWN,
    "allow": UserRole.ALLOW,
    "blocked": UserRole.BLOCKED,
    "staff": UserRole.STAFF,
}
_MODE_BY_NAME = {
    "pm": RestrictMode.PM_ONLY,
    "mention": RestrictMode.MENTION_ONLY,
    "both": RestrictMode.BOTH,
}


def _parse_user_id(raw: str) -> int | None:
    raw = raw.lstrip("@").strip()
    if not raw.lstrip("-").isdigit():
        return None
    try:
        return int(raw)
    except ValueError:
        return None


async def _resolve_target_id(raw: str, user_repo: UserRepository) -> int | None:
    """Resolve a numeric id or @username to an existing user id.

    Unknown references return None, so admins cannot act on a user the bot
    has never seen.
    """
    numeric = _parse_user_id(raw)
    if numeric is not None:
        user = await user_repo.get(numeric)
        return user.id if user else None
    name = raw.lstrip("@").strip()
    if not name:
        return None
    user = await user_repo.get_by_username(name)
    return user.id if user else None


_UNKNOWN_USER_REPLY = texts.UNKNOWN_USER

# ── FSM: user management from the inline menu (id/@username → role/reason) ────


class UsersState(StatesGroup):
    waiting_for_target = State()
    waiting_for_role = State()
    waiting_for_reason = State()


_ROLE_BTN_BY_ROLE = {
    UserRole.UNKNOWN: (texts.USERS_ROLE_BTN_UNKNOWN, "unknown"),
    UserRole.ALLOW: (texts.USERS_ROLE_BTN_ALLOW, "allow"),
    UserRole.BLOCKED: (texts.USERS_ROLE_BTN_BLOCKED, "blocked"),
    UserRole.STAFF: (texts.USERS_ROLE_BTN_STAFF, "staff"),
}


async def start_users_set(message: Message, state: FSMContext) -> None:
    await state.set_state(UsersState.waiting_for_target)
    await state.update_data(action="set")
    await message.answer(texts.USERS_ASK_TARGET)


async def start_users_block(message: Message, state: FSMContext) -> None:
    await state.set_state(UsersState.waiting_for_target)
    await state.update_data(action="block")
    await message.answer(texts.USERS_ASK_TARGET)


async def start_users_unblock(message: Message, state: FSMContext) -> None:
    await state.set_state(UsersState.waiting_for_target)
    await state.update_data(action="unblock")
    await message.answer(texts.USERS_ASK_TARGET)


@router.message(UsersState.waiting_for_target, F.chat.type == ChatType.PRIVATE)
async def users_target_input(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        await state.clear()
        await temp_reply(message, texts.CANCELLED)
        return

    action = (await state.get_data()).get("action")
    async with session_factory() as session:
        repo = UserRepository(session)
        target_id = await _resolve_target_id(raw, repo)
    if target_id is None:
        await temp_reply(message, texts.USERS_ASK_TARGET_BAD)
        return

    await state.update_data(target_id=target_id)

    if action == "set":
        await state.set_state(UsersState.waiting_for_role)
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=RolePickCallback(role=key).pack(),
                    )
                    for label, key in [
                        _ROLE_BTN_BY_ROLE[UserRole.UNKNOWN],
                        _ROLE_BTN_BY_ROLE[UserRole.ALLOW],
                    ]
                ],
                [
                    InlineKeyboardButton(
                        text=label,
                        callback_data=RolePickCallback(role=key).pack(),
                    )
                    for label, key in [
                        _ROLE_BTN_BY_ROLE[UserRole.BLOCKED],
                        _ROLE_BTN_BY_ROLE[UserRole.STAFF],
                    ]
                ],
            ]
        )
        await message.answer(texts.USERS_ASK_ROLE.format(ref=html_escape(raw)), reply_markup=kb)
        return

    if action == "block":
        await state.set_state(UsersState.waiting_for_reason)
        await message.answer(texts.USERS_ASK_REASON)
        return

    # action == "unblock"
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.set_role(target_id, UserRole.ALLOW)
        await session.commit()
    await state.clear()
    await temp_reply(message, texts.USERS_UNBLOCKED.format(id=target_id))


@router.callback_query(RolePickCallback.filter())
async def users_role_picked(
    query: CallbackQuery,
    callback_data: RolePickCallback,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    current = await state.get_state()
    if current != UsersState.waiting_for_role.state:
        await safe_answer(query, texts.USERS_STALE, show_alert=True)
        return

    role = _ROLE_BY_NAME.get(callback_data.role)
    if role is None:
        await safe_answer(query)
        return

    data = await state.get_data()
    target_id = data.get("target_id")
    if not isinstance(target_id, int):
        await safe_answer(query, texts.USERS_STALE, show_alert=True)
        return
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.set_role(
            target_id,
            role,
            blocked_by=query.from_user.id if query.from_user else None,
        )
        await session.commit()
    await state.clear()

    await safe_answer(query)
    message = query.message
    if isinstance(message, Message):
        await message.edit_text(texts.USERS_ROLE_SET.format(id=target_id, role=role.name))
    _log.info(
        "user_role_set_menu",
        target_id=target_id,
        role=role.name,
        by=query.from_user.id if query.from_user else 0,
    )


@router.message(UsersState.waiting_for_role, F.chat.type == ChatType.PRIVATE)
async def users_role_text_fallback(message: Message, state: FSMContext) -> None:
    """Text typed instead of a role button; nudge back to the keyboard."""
    if (message.text or "").startswith("/"):
        await state.clear()
        await temp_reply(message, texts.CANCELLED)
        return
    await temp_reply(message, texts.USERS_PICK_ROLE_HINT)


@router.message(UsersState.waiting_for_reason, F.chat.type == ChatType.PRIVATE)
async def users_reason_input(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        await state.clear()
        await temp_reply(message, texts.CANCELLED)
        return

    reason = "" if raw == "-" else raw
    data = await state.get_data()
    target_id = data.get("target_id")
    if not isinstance(target_id, int):
        await state.clear()
        await temp_reply(message, texts.USERS_STALE)
        return
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.set_role(
            target_id,
            UserRole.BLOCKED,
            block_reason=reason,
            blocked_by=message.from_user.id if message.from_user else None,
        )
        await session.commit()
    await state.clear()
    await temp_reply(
        message,
        texts.USERS_BLOCKED.format(
            id=target_id,
            reason=html_escape(reason or texts.USERS_BLOCKED_NO_REASON),
            mode=RestrictMode.BOTH.name,
        ),
    )


# ── FSM: categories from the inline menu (current list as a hint) ─────────────


class CategoriesState(StatesGroup):
    waiting_for_name = State()
    waiting_for_id = State()
    waiting_for_order = State()


async def _categories_hint(session_factory: async_sessionmaker[AsyncSession]) -> str:
    return texts.CATEGORIES_CURRENT.format(list=await _render_categories_list(session_factory))


async def start_categories_add(
    message: Message, state: FSMContext, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await state.set_state(CategoriesState.waiting_for_name)
    await message.answer(await _categories_hint(session_factory) + texts.CATEGORIES_ADD_ASK)


async def _start_categories_id_flow(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
    *,
    action: str,
    ask_text: str,
) -> None:
    await state.set_state(CategoriesState.waiting_for_id)
    await state.update_data(action=action)
    await message.answer(await _categories_hint(session_factory) + ask_text)


async def start_categories_remove(
    message: Message, state: FSMContext, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _start_categories_id_flow(
        message, state, session_factory, action="remove", ask_text=texts.CATEGORIES_REMOVE_ASK
    )


async def start_categories_hide(
    message: Message, state: FSMContext, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _start_categories_id_flow(
        message, state, session_factory, action="hide", ask_text=texts.CATEGORIES_HIDE_ASK
    )


async def start_categories_show(
    message: Message, state: FSMContext, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _start_categories_id_flow(
        message, state, session_factory, action="show", ask_text=texts.CATEGORIES_SHOW_ASK
    )


async def start_categories_order(
    message: Message, state: FSMContext, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await state.set_state(CategoriesState.waiting_for_order)
    await message.answer(await _categories_hint(session_factory) + texts.CATEGORIES_ORDER_ASK)


@router.message(CategoriesState.waiting_for_name, F.chat.type == ChatType.PRIVATE)
async def categories_name_input(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        await state.clear()
        await temp_reply(message, texts.CANCELLED)
        return

    async with session_factory() as session:
        repo = CategoryRepository(session)
        if await repo.get_by_name(raw) is not None:
            await temp_reply(message, texts.CATEGORIES_EXISTS)
            return
        await repo.add(raw)
        await session.commit()
    await state.clear()
    await temp_reply(message, texts.CATEGORIES_ADDED.format(name=html_escape(raw)))


@router.message(CategoriesState.waiting_for_id, F.chat.type == ChatType.PRIVATE)
async def categories_id_input(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        await state.clear()
        await temp_reply(message, texts.CANCELLED)
        return

    cat_id = _parse_user_id(raw)
    if cat_id is None:
        await temp_reply(message, texts.CATEGORIES_BAD_ID_INPUT)
        return

    action = (await state.get_data()).get("action")
    async with session_factory() as session:
        repo = CategoryRepository(session)
        cat = await repo.get_by_id(cat_id)
        if cat is None:
            await temp_reply(message, texts.CATEGORIES_NOT_FOUND)
            return
        if action == "remove":
            name = cat.name
            await session.delete(cat)
            await session.commit()
            await state.clear()
            await temp_reply(message, texts.CATEGORIES_REMOVED.format(name=html_escape(name)))
            return
        cat.is_active = action == "show"
        await session.commit()

    await state.clear()
    await temp_reply(
        message, texts.CATEGORIES_SHOWN if action == "show" else texts.CATEGORIES_HIDDEN
    )


def _parse_order_pairs(raw: str) -> list[tuple[int, int]] | None:
    """Parse "id:order, id:order, …" into pairs; None when the format is wrong."""
    pairs: list[tuple[int, int]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        left, sep, right = part.partition(":")
        if not sep:
            return None
        if not (left.strip().lstrip("-").isdigit() and right.strip().lstrip("-").isdigit()):
            return None
        pairs.append((int(left.strip()), int(right.strip())))
    return pairs or None


@router.message(CategoriesState.waiting_for_order, F.chat.type == ChatType.PRIVATE)
async def categories_order_input(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    raw = (message.text or "").strip()
    if raw.startswith("/"):
        await state.clear()
        await temp_reply(message, texts.CANCELLED)
        return

    pairs = _parse_order_pairs(raw)
    if pairs is None:
        await temp_reply(message, texts.CATEGORIES_ORDER_PARSE_BAD)
        return

    async with session_factory() as session:
        repo = CategoryRepository(session)
        for cat_id, order in pairs:
            cat = await repo.get_by_id(cat_id)
            if cat is None:
                await temp_reply(message, texts.CATEGORIES_NOT_FOUND)
                return
            cat.display_order = order
        await session.commit()

    await state.clear()
    await temp_reply(message, texts.CATEGORIES_ORDER_DONE_ALL)


@router.message(Command("users"), F.chat.type == ChatType.PRIVATE)
async def cmd_users(
    message: Message,
    command: CommandObject,
    access: AccessService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not await require_staff(message, access):
        return

    args = (command.args or "").split()
    if not args:
        await temp_reply(message, texts.USERS_HELP)
        return

    sub = args[0].lower()

    if sub == "list":
        await message.answer(
            await _render_users_list(session_factory),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return

    if sub == "set":
        if len(args) < 3:
            await temp_reply(message, texts.USERS_SET_EXAMPLE)
            return
        role_name = args[2].lower()
        if role_name not in _ROLE_BY_NAME:
            await temp_reply(message, texts.USERS_ROLE_NAMES)
            return
        role = _ROLE_BY_NAME[role_name]
        reason = " ".join(args[3:]) if len(args) > 3 else ""
        restrict = RestrictMode.BOTH
        if role == UserRole.BLOCKED:
            # Optional trailing token: pm|mention|both
            tokens = reason.rsplit(maxsplit=1)
            if tokens and tokens[-1].lower() in _MODE_BY_NAME:
                restrict = _MODE_BY_NAME[tokens[-1].lower()]
                reason = tokens[0]
        async with session_factory() as session:
            repo = UserRepository(session)
            target_id = await _resolve_target_id(args[1], repo)
            if target_id is None:
                await temp_reply(message, _UNKNOWN_USER_REPLY)
                return
            await repo.set_role(
                target_id,
                role,
                block_reason=reason if role == UserRole.BLOCKED else "",
                restrict_mode=restrict if role == UserRole.BLOCKED else RestrictMode.BOTH,
                blocked_by=(message.from_user.id if message.from_user else None)
                if role == UserRole.BLOCKED
                else None,
            )
            await session.commit()
        await temp_reply(
            message,
            texts.USERS_ROLE_SET.format(id=target_id, role=role.name)
            + (
                texts.USERS_ROLE_SET_REASON_SUFFIX.format(reason=html_escape(reason))
                if role == UserRole.BLOCKED and reason
                else ""
            ),
        )
        _log.info(
            "user_role_set",
            target_id=target_id,
            role=role.name,
            by=message.from_user.id if message.from_user else 0,
        )
        return

    if sub == "block":
        if len(args) < 2:
            await temp_reply(message, texts.USERS_BLOCK_EXAMPLE)
            return
        reason = " ".join(args[2:]) if len(args) > 2 else ""
        restrict = RestrictMode.BOTH
        if reason:
            tokens = reason.rsplit(maxsplit=1)
            if tokens and tokens[-1].lower() in _MODE_BY_NAME:
                restrict = _MODE_BY_NAME[tokens[-1].lower()]
                reason = tokens[0]
        async with session_factory() as session:
            repo = UserRepository(session)
            target_id = await _resolve_target_id(args[1], repo)
            if target_id is None:
                await temp_reply(message, _UNKNOWN_USER_REPLY)
                return
            await repo.set_role(
                target_id,
                UserRole.BLOCKED,
                block_reason=reason,
                restrict_mode=restrict,
                blocked_by=message.from_user.id if message.from_user else None,
            )
            await session.commit()
        await temp_reply(
            message,
            texts.USERS_BLOCKED.format(
                id=target_id,
                reason=html_escape(reason or texts.USERS_BLOCKED_NO_REASON),
                mode=restrict.name,
            ),
        )
        return

    if sub == "unblock":
        if len(args) < 2:
            await temp_reply(message, texts.USERS_UNBLOCK_EXAMPLE)
            return
        async with session_factory() as session:
            repo = UserRepository(session)
            target_id = await _resolve_target_id(args[1], repo)
            if target_id is None:
                await temp_reply(message, _UNKNOWN_USER_REPLY)
                return
            await repo.set_role(target_id, UserRole.ALLOW)
            await session.commit()
        await temp_reply(message, texts.USERS_UNBLOCKED.format(id=target_id))
        return

    await temp_reply(message, texts.USERS_HELP)


@router.message(Command("admin_contacts"), F.chat.type == ChatType.PRIVATE)
async def cmd_admin_contacts(
    message: Message,
    command: CommandObject,
    access: AccessService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not await require_staff(message, access):
        return

    args = (command.args or "").split()
    if not args:
        await temp_reply(message, texts.CONTACTS_HELP)
        return

    sub = args[0].lower()

    if sub == "list":
        await message.answer(
            await _render_admin_contacts_list(session_factory),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return

    if sub == "add":
        if len(args) < 3:
            await temp_reply(message, texts.CONTACTS_ADD_EXAMPLE)
            return
        async with session_factory() as session:
            user_repo = UserRepository(session)
            target_id = await _resolve_target_id(args[1], user_repo)
            if target_id is None:
                await temp_reply(message, texts.CONTACTS_USER_NOT_FOUND)
                return
            public_role = args[2]
            comment = " ".join(args[3:]) if len(args) > 3 else ""
            repo = AdminContactRepository(session)
            await repo.upsert(
                user_id=target_id,
                public_role=public_role,
                comment=comment,
            )
            await session.commit()
        await temp_reply(message, texts.CONTACTS_SAVED.format(id=target_id))
        return

    if sub == "remove":
        if len(args) < 2:
            await temp_reply(message, texts.CONTACTS_REMOVE_EXAMPLE)
            return
        target_id = _parse_user_id(args[1])
        if target_id is None:
            await temp_reply(message, texts.CONTACTS_BAD_ID)
            return
        async with session_factory() as session:
            repo = AdminContactRepository(session)
            await repo.remove(target_id)
            await session.commit()
        await temp_reply(message, texts.CONTACTS_REMOVED.format(id=target_id))
        return

    if sub == "order":
        if len(args) < 3:
            await temp_reply(message, texts.CONTACTS_ORDER_EXAMPLE)
            return
        target_id = _parse_user_id(args[1])
        if target_id is None:
            await temp_reply(message, texts.CONTACTS_BAD_ID)
            return
        try:
            order = int(args[2])
        except ValueError:
            await temp_reply(message, texts.CONTACTS_ORDER_BAD)
            return
        async with session_factory() as session:
            repo = AdminContactRepository(session)
            existing = await repo.get_by_user_id(target_id)
            if existing is None:
                await temp_reply(message, texts.CONTACTS_ORDER_MISSING)
                return
            existing.display_order = order
            await session.commit()
        await temp_reply(message, texts.CONTACTS_ORDER_DONE.format(id=target_id, order=order))
        return

    await temp_reply(message, texts.CONTACTS_HELP)


@router.message(Command("categories"), F.chat.type == ChatType.PRIVATE)
async def cmd_categories(
    message: Message,
    command: CommandObject,
    access: AccessService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not await require_staff(message, access):
        return

    args = (command.args or "").strip()
    if not args:
        await temp_reply(message, texts.CATEGORIES_HELP)
        return

    parts = args.split(maxsplit=1)
    sub = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if sub == "list":
        await message.answer(
            await _render_categories_list(session_factory),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return

    if sub == "add":
        if not rest:
            await temp_reply(message, texts.CATEGORIES_ADD_EXAMPLE)
            return
        async with session_factory() as session:
            repo = CategoryRepository(session)
            if await repo.get_by_name(rest) is not None:
                await temp_reply(message, texts.CATEGORIES_EXISTS)
                return
            await repo.add(rest)
            await session.commit()
        await temp_reply(message, texts.CATEGORIES_ADDED.format(name=html_escape(rest)))
        return

    if sub in ("remove", "delete"):
        cat_id = _parse_user_id(rest)
        if cat_id is None:
            await temp_reply(
                message,
                texts.CATEGORIES_REMOVE_HINT,
            )
            return
        async with session_factory() as session:
            repo = CategoryRepository(session)
            cat = await repo.get_by_id(cat_id)
            if cat is None:
                await temp_reply(message, texts.CATEGORIES_NOT_FOUND)
                return
            name = cat.name
            await session.delete(cat)
            await session.commit()
        await temp_reply(message, texts.CATEGORIES_REMOVED.format(name=html_escape(name)))
        return

    if sub == "order":
        tokens = rest.split()
        if len(tokens) < 2:
            await temp_reply(message, texts.CATEGORIES_ORDER_EXAMPLE)
            return
        cat_id = _parse_user_id(tokens[0])
        try:
            order = int(tokens[1])
        except ValueError:
            await temp_reply(message, texts.CATEGORIES_ORDER_BAD)
            return
        if cat_id is None:
            await temp_reply(message, texts.CATEGORIES_BAD_ID)
            return
        async with session_factory() as session:
            repo = CategoryRepository(session)
            cat = await repo.get_by_id(cat_id)
            if cat is None:
                await temp_reply(message, texts.CATEGORIES_NOT_FOUND)
                return
            cat.display_order = order
            await session.commit()
        await temp_reply(message, texts.CATEGORIES_ORDER_DONE.format(id=cat_id, order=order))
        return

    if sub in ("hide", "show"):
        cat_id = _parse_user_id(rest)
        if cat_id is None:
            await temp_reply(message, texts.CATEGORIES_SHOW_EXAMPLE.format(sub=sub))
            return
        async with session_factory() as session:
            repo = CategoryRepository(session)
            cat = await repo.get_by_id(cat_id)
            if cat is None:
                await temp_reply(message, texts.CATEGORIES_NOT_FOUND)
                return
            cat.is_active = sub == "show"
            await session.commit()
        await temp_reply(
            message, (texts.CATEGORIES_SHOWN if sub == "show" else texts.CATEGORIES_HIDDEN)
        )
        return

    await temp_reply(message, texts.CATEGORIES_HELP)


@router.message(Command("stats"), F.chat.type == ChatType.PRIVATE)
async def cmd_stats(
    message: Message,
    command: CommandObject,
    access: AccessService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not await require_staff(message, access):
        return

    args = (command.args or "").strip()

    if not args or args.isdigit():
        limit = int(args) if args.isdigit() else 10
        limit = max(1, min(limit, 50))
        await message.answer(
            await _render_stats_recent(session_factory, limit),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return

    if args.lower() == "user" or args.lower().startswith("user "):
        ref = args[4:].strip() if args.lower().startswith("user ") else ""
        if not ref:
            await temp_reply(message, texts.STATS_USER_EXAMPLE)
            return
        async with session_factory() as session:
            repo = PostStatRepository(session)
            user_repo = UserRepository(session)
            target_id = await _resolve_target_id(ref, user_repo)
            if target_id is None:
                await temp_reply(message, texts.STATS_USER_NOT_FOUND)
                return
            user = await user_repo.get(target_id)
            total = await repo.count_by_author(target_id)
            if total == 0:
                await temp_reply(message, texts.STATS_USER_EMPTY)
                return
            posts = await repo.get_by_author(target_id, 10)
        if user is not None:
            name = f"@{user.username}" if user.username else (user.first_name or f"id:{user.id}")
        else:
            name = str(target_id)
        lines = [texts.STATS_USER_HEADER.format(name=html_escape(name), total=total)]
        for i, p in enumerate(posts, 1):
            lines.append(f"{i}) {_post_line(p)}")
        await message.answer(
            "\n".join(lines), link_preview_options=LinkPreviewOptions(is_disabled=True)
        )
        return

    if args.lower() == "categories":
        await message.answer(
            await _render_stats_categories(session_factory),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return

    if args.lower() == "users":
        await message.answer(
            await _render_stats_users(session_factory),
            link_preview_options=LinkPreviewOptions(is_disabled=True),
        )
        return

    await temp_reply(message, texts.STATS_HELP)


def _post_line(p: PublishedPost) -> str:
    when = p.published_at.strftime("%d.%m %H:%M") if p.published_at else ""
    head = (
        f"🏷 <b>{html_escape(p.category or texts.STATS_CATEGORY_NONE)}</b> · "
        f"👤 {html_escape(p.author_name)} · {html_escape(_stats_source(p))} "
        f"<i>({when})</i>"
    )
    if p.preview:
        head += f"\n<blockquote>{html_escape(p.preview)}</blockquote>"
    return head


def _stats_source(post: PublishedPost) -> str:
    if post.source == "pm":
        return texts.STATS_SOURCE_PM
    return (
        texts.STATS_SOURCE_CHAT.format(name=post.source_chat_name)
        if post.source_chat_name
        else texts.STATS_SOURCE_UNKNOWN
    )


async def _render_users_list(session_factory: async_sessionmaker[AsyncSession]) -> str:
    async with session_factory() as session:
        repo = UserRepository(session)
        users = await repo.get_all()
    if not users:
        return texts.USERS_LIST_EMPTY
    lines = []
    for u in users:
        name = html_escape(
            " ".join(filter(None, [u.first_name, u.last_name])) or u.username or f"id:{u.id}"
        )
        handle = html_escape(f"@{u.username}") if u.username else "—"
        lines.append(
            f"• {name} ({handle}) <code>id:{u.id}</code> — <b>{html_escape(role_label_ru(u.role))}</b>"
        )
    return "\n".join(lines)


async def _render_admin_contacts_list(session_factory: async_sessionmaker[AsyncSession]) -> str:
    async with session_factory() as session:
        repo = AdminContactRepository(session)
        user_repo = UserRepository(session)
        contacts = await repo.get_all()
        if not contacts:
            return texts.CONTACTS_LIST_EMPTY
        lines = []
        for c in contacts:
            user = await user_repo.get(c.user_id)
            handle = (
                html_escape(f"@{user.username}") if user and user.username else f"id:{c.user_id}"
            )
            comment = f" — {html_escape(c.comment)}" if c.comment else ""
            lines.append(
                f"• {handle} — {html_escape(c.public_role)} (order={c.display_order}){comment}"
            )
    return "\n".join(lines)


async def _render_categories_list(session_factory: async_sessionmaker[AsyncSession]) -> str:
    async with session_factory() as session:
        repo = CategoryRepository(session)
        cats = await repo.get_all()
        if not cats:
            return texts.CATEGORIES_LIST_EMPTY
        lines = []
        for c in cats:
            status = "" if c.is_active else texts.CATEGORIES_HIDDEN_MARKER
            lines.append(
                texts.CATEGORY_LINE.format(
                    id=c.id, name=html_escape(c.name), order=c.display_order, status=status
                )
            )
    return "\n".join(lines)


async def _render_stats_recent(
    session_factory: async_sessionmaker[AsyncSession], limit: int = 10
) -> str:
    async with session_factory() as session:
        repo = PostStatRepository(session)
        posts = await repo.get_recent(limit)
        total = await repo.count()
    if not posts:
        return texts.STATS_RECENT_EMPTY
    lines = [texts.STATS_RECENT_HEADER.format(total=total)]
    for i, p in enumerate(posts, 1):
        lines.append(f"{i}) {_post_line(p)}")
    return "\n".join(lines)


async def _render_stats_categories(session_factory: async_sessionmaker[AsyncSession]) -> str:
    async with session_factory() as session:
        repo = PostStatRepository(session)
        rows = await repo.count_by_category()
    if not rows:
        return texts.STATS_RECENT_EMPTY
    lines = [texts.STATS_BY_CATEGORY_HEADER]
    for name, count in rows:
        lines.append(f"• {html_escape(name or texts.STATS_CATEGORY_NONE)} — {count}")
    return "\n".join(lines)


async def _render_stats_users(session_factory: async_sessionmaker[AsyncSession]) -> str:
    async with session_factory() as session:
        repo = PostStatRepository(session)
        rows = await repo.count_by_user()
    if not rows:
        return texts.STATS_RECENT_EMPTY
    lines = [texts.STATS_BY_USER_HEADER]
    for _uid, name, count in rows:
        lines.append(f"• {html_escape(name)} — {count}")
    return "\n".join(lines)
