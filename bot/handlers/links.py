"""Community links: /links command + FSM for the "Ссылки" menu.

Admins set the three community links shown at the bottom of the inline menu:
rules ("Правила публикации постов"), channel ("Канал"), chat ("Основной чат").
Values live in the single-row `CommunityLinks` table; until set, the menu shows
a "ссылка не заполнена" placeholder button.

Command forms:
  /links: show current links and usage
  /links rules|channel|chat <url>: set a link
  /links clear rules|channel|chat: clear a link
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import LinkPreviewOptions, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import texts
from bot.db.models import CommunityLinks
from bot.db.repo.links import LINK_FIELDS, LinksRepository, link_label
from bot.logging_setup import get_logger
from bot.services.access import AccessService
from bot.services.access_messages import require_staff
from bot.utils.formatting import html_escape
from bot.utils.replies import temp_reply

router = Router(name="links")
_log = get_logger("bot.links")


class LinksState(StatesGroup):
    waiting_for_url = State()


def render_links_text(links: CommunityLinks) -> str:
    def fmt(url: str | None) -> str:
        return html_escape(url) if url else texts.LINKS_EMPTY_VALUE

    return (
        texts.LINKS_HEADER
        + texts.LINKS_LINE.format(
            icon="📜", label=texts.LINK_LABEL_RULES, value=fmt(links.rules_url)
        )
        + texts.LINKS_LINE.format(
            icon="📢", label=texts.LINK_LABEL_CHANNEL, value=fmt(links.channel_url)
        )
        + texts.LINKS_LINE.format(
            icon="💬", label=texts.LINK_LABEL_CHAT, value=fmt(links.main_chat_url)
        )
        + "\n"
        + texts.LINKS_USAGE
    )


def _valid_url(text: str) -> bool:
    return text.startswith(("http://", "https://", "t.me/", "tg://"))


@router.message(Command("links"), F.chat.type == ChatType.PRIVATE)
async def cmd_links(
    message: Message,
    command: CommandObject,
    access: AccessService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not await require_staff(message, access, deny_text=texts.LINKS_ADMIN_ONLY):
        return

    args = (command.args or "").strip()
    async with session_factory() as session:
        repo = LinksRepository(session)

        if not args:
            links = await repo.get()
            await message.answer(
                render_links_text(links),
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
            return

        parts = args.split(maxsplit=1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub == "clear":
            if rest not in LINK_FIELDS:
                await temp_reply(message, texts.LINKS_CLEAR_KEY)
                return
            links = await repo.clear(rest)
            await session.commit()
            await temp_reply(message, texts.LINKS_CLEARED.format(label=link_label(rest)))
            _log.info("link_cleared", key=rest, by=message.from_user.id if message.from_user else 0)
            return

        if sub in LINK_FIELDS:
            if not rest or not _valid_url(rest):
                await temp_reply(
                    message,
                    texts.LINKS_SET_EXAMPLE.format(key=sub),
                )
                return
            links = await repo.set(sub, rest)
            await session.commit()
            await message.answer(
                render_links_text(links),
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
            _log.info("link_set", key=sub, by=message.from_user.id if message.from_user else 0)
            return

    await temp_reply(message, texts.LINKS_BAD_KEY)


@router.message(LinksState.waiting_for_url, F.chat.type == ChatType.PRIVATE)
async def links_url_input(
    message: Message,
    state: FSMContext,
    access: AccessService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        await state.clear()
        await temp_reply(message, texts.CANCELLED)
        return

    if not _valid_url(text):
        await message.reply(texts.LINKS_BAD_URL)
        return

    data = await state.get_data()
    key = data.get("link_key")
    if key not in LINK_FIELDS:
        await state.clear()
        await temp_reply(message, texts.LINKS_UNKNOWN_KEY)
        return

    async with session_factory() as session:
        repo = LinksRepository(session)
        links = await repo.set(key, text)
        await session.commit()

    await state.clear()
    await message.answer(
        texts.LINKS_SAVED.format(label=link_label(key)) + render_links_text(links),
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
