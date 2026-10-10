"""Chat registration wizard: /add_chat in PM, adds a permanent invite link.

Sequential FSM wizard: id, name, link. The bot shows the current state for an
already-registered id and warns on a name conflict. The link is user-provided,
so it survives the bot losing admin rights, unlike onboarding's exported links.
"""

from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import texts
from bot.db.repo.chats import ChatRepository
from bot.logging_setup import get_logger
from bot.services.access import AccessService, PublishChannel
from bot.services.access_messages import build_guest_message
from bot.services.membership import MembershipService
from bot.utils.formatting import html_escape
from bot.utils.replies import temp_reply
from bot.utils.telegram_links import parse_chat_link

router = Router(name="add_chat")
_log = get_logger("bot.add_chat")

CANCEL_HINT = texts.ADD_CHAT_CANCEL_HINT


class AddChatState(StatesGroup):
    waiting_for_id = State()
    waiting_for_name = State()
    waiting_for_link = State()


_NUM_RE = re.compile(r"-?\d+")

_ID_HOWTO = texts.ADD_CHAT_ID_HOWTO


def _is_cancel(text: str) -> bool:
    """True for `/cancel` (with optional @botname suffix)."""
    return text == "/cancel" or text.startswith("/cancel@")


def _parse_id(text: str) -> int | None:
    """Parse a numeric chat id from free text.

    Prefers a negative token (chat ids are negative), else the last number.
    """
    matches = list(_NUM_RE.finditer(text))
    if not matches:
        return None
    negative = [m for m in matches if m.group(0).startswith("-")]
    target = negative[-1] if negative else matches[-1]
    try:
        return int(target.group(0))
    except ValueError:
        return None


def _intro_text() -> str:
    return texts.ADD_CHAT_INTRO.format(howto=_ID_HOWTO) + CANCEL_HINT


async def start_add_chat(state: FSMContext, message: Message) -> None:
    """Ask for the chat id and enter the wizard."""
    await state.set_state(AddChatState.waiting_for_id)
    await message.answer(_intro_text())


async def _gate_membership(
    message: Message,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> bool:
    """True if the sender may add a chat (STAFF or main-channel member)."""
    user = message.from_user
    if user is None:
        return False
    decision = await access.resolve(
        user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        channel=PublishChannel.PM,
    )
    if not decision.is_staff and not await membership.is_member(user.id):
        await message.answer(await build_guest_message(session_factory))
        return False
    return True


@router.message(Command("add_chat"), F.chat.type == ChatType.PRIVATE)
async def cmd_add_chat(
    message: Message,
    state: FSMContext,
    access: AccessService,
    membership: MembershipService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not await _gate_membership(message, access, membership, session_factory):
        return
    await start_add_chat(state, message)


@router.message(AddChatState.waiting_for_id, F.chat.type == ChatType.PRIVATE)
async def add_chat_id_input(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        await state.clear()
        if _is_cancel(text):
            await message.answer(texts.ADD_CHAT_CANCELLED)
        return  # other commands are handled earlier (common router)

    chat_id = _parse_id(text)
    if chat_id is None:
        await state.set_state(AddChatState.waiting_for_id)
        await temp_reply(message, texts.ADD_CHAT_BAD_ID.format(howto=_ID_HOWTO) + CANCEL_HINT)
        return

    await state.update_data(pending_chat_id=chat_id)

    async with session_factory() as session:
        repo = ChatRepository(session)
        existing = await repo.get_by_chat_id(chat_id)

    if existing is not None:
        info = (
            texts.ADD_CHAT_EXISTS_WITH_LINK if existing.join_link else texts.ADD_CHAT_EXISTS_NO_LINK
        )
        await message.answer(info.format(name=html_escape(existing.exact_name)))

    await state.set_state(AddChatState.waiting_for_name)
    await message.answer(texts.ADD_CHAT_ASK_NAME + CANCEL_HINT)


@router.message(AddChatState.waiting_for_name, F.chat.type == ChatType.PRIVATE)
async def add_chat_name_input(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    chat_id = data.get("pending_chat_id")
    name = (message.text or "").strip()
    if name.startswith("/"):
        await state.clear()
        if _is_cancel(name):
            await message.answer(texts.ADD_CHAT_CANCELLED)
        return

    if not isinstance(chat_id, int):
        await state.clear()
        return

    await state.update_data(pending_name=name)

    warning = ""
    async with session_factory() as session:
        repo = ChatRepository(session)
        by_name = await repo.get_by_name(name)
        if by_name is not None and by_name.chat_id != chat_id:
            warning = texts.ADD_CHAT_NAME_CONFLICT.format(name=html_escape(name)) + "\n\n"

    await state.set_state(AddChatState.waiting_for_link)
    await message.answer(warning + texts.ADD_CHAT_ASK_LINK + CANCEL_HINT)


@router.message(AddChatState.waiting_for_link, F.chat.type == ChatType.PRIVATE)
async def add_chat_link_input(
    message: Message,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    chat_id = data.get("pending_chat_id")
    name = str(data.get("pending_name") or "")
    link = (message.text or "").strip()
    if link.startswith("/"):
        await state.clear()
        if _is_cancel(link):
            await message.answer(texts.ADD_CHAT_CANCELLED)
        return

    if not isinstance(chat_id, int):
        await state.clear()
        return

    if parse_chat_link(link) is None:
        await state.set_state(AddChatState.waiting_for_link)
        await temp_reply(message, texts.ADD_CHAT_BAD_LINK + CANCEL_HINT)
        return

    await state.clear()

    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(
            chat_id=chat_id,
            exact_name=name,
            join_link=link,
            added_by=message.from_user.id if message.from_user else None,
            link_source="pm",
        )
        await session.commit()

    _log.info(
        "chat_added_via_wizard",
        chat_id=chat_id,
        title=name,
        added_by=message.from_user.id if message.from_user else None,
    )
    await message.answer(texts.ADD_CHAT_SUCCESS.format(name=html_escape(name)))
