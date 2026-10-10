"""Repost handler: reply + @bot mention in non-private chats.

Posting strategy: text → send_message; single media → copy_message with the
signature as caption; album → send_media_group when the full group is cached,
otherwise a single-item copy.
"""

from __future__ import annotations

from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LinkPreviewOptions,
    Message,
    User,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import texts
from bot.config import Settings
from bot.db.models import SavedChat
from bot.db.repo.categories import CategoryRepository
from bot.logging_setup import get_logger
from bot.services.access_messages import blocked_chat_lines
from bot.services.album_publisher import publish_album
from bot.services.categories import active_categories
from bot.services.chat_lookup import ChatLookupService
from bot.services.content_types import classify_content, extract_file_id, unsupported_reply
from bot.services.media_group_cache import MediaGroupCache
from bot.services.post_builder import (
    PostSignature,
    author_display_name,
    build_signature,
    caption_over_limit,
    compose_html,
    render_message_body,
)
from bot.services.post_stats import record_post
from bot.utils.callbacks import CategoryCallback, RepostPollCallback, category_keyboard
from bot.utils.formatting import html_escape, make_preview
from bot.utils.replies import react_ok, safe_answer, schedule_delete, temp_reply

router = Router(name="repost")
_log = get_logger("bot.repost")


class RepostState(StatesGroup):
    waiting_for_category = State()
    waiting_for_poll_confirm = State()


def is_repost_trigger(message: Message, bot_name: str, trigger_phrases: list[str]) -> bool:
    """True if `message` is a reply in a non-private chat that should be reposted.

    Triggers are:
    - a mention of @bot_name (in `entities` or `caption_entities`), or
    - a trigger phrase (case-insensitive), e.g. "В движухи!".

    Either way the message must be a reply to another message.
    """
    if message.chat.type == ChatType.PRIVATE:
        return False
    if not message.reply_to_message:
        return False
    text = message.text or message.caption or ""
    # a mention can be in text or caption entities; check both
    name = bot_name.lstrip("@").lower()
    entities = (message.entities or []) + (message.caption_entities or [])
    for ent in entities:
        if ent.type != "mention":
            continue
        mention = text[ent.offset : ent.offset + ent.length].lstrip("@").lower()
        if mention == name:
            return True

    # Trigger phrase (case-insensitive, ignoring trailing punctuation).
    normalized = text.strip().lower().rstrip("!. ")
    for phrase in trigger_phrases:
        p = (phrase or "").strip().lower().rstrip("!. ")
        if p and normalized == p:
            return True
    return False


def registration_hint(saved_chat: SavedChat | None) -> str:
    """Appendix for reposts from chats without a registered invite link."""
    if saved_chat is not None and saved_chat.join_link:
        return ""
    return "\n\n" + texts.CHAT_NOT_REGISTERED_HINT


@router.message(F.reply_to_message, F.chat.type != ChatType.PRIVATE)
async def repost_via_reply_mention(
    message: Message,
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    media_group_cache: MediaGroupCache,
    state: FSMContext,
) -> None:
    # let command handlers process commands
    if message.text and message.text.startswith("/"):
        return

    chat_id = message.chat.id
    msg_id = message.message_id

    if not is_repost_trigger(message, settings.bot_name, settings.repost_trigger_phrases):
        _log.debug(
            "repost_skip_not_trigger",
            chat_id=chat_id,
            message_id=msg_id,
            bot_name=settings.bot_name,
            text_preview=(message.text or "")[:80],
            entities=[
                (e.type, (message.text or "")[e.offset : e.offset + e.length])
                for e in (message.entities or [])
            ],
        )
        return

    source = message.reply_to_message
    if source is None:
        return

    _log.info(
        "repost_request",
        chat_id=chat_id,
        message_id=msg_id,
        source_message_id=source.message_id,
        source_media_group_id=source.media_group_id,
        source_content_type="text"
        if source.text is not None
        else ("photo" if source.photo else "video" if source.video else "other"),
    )

    lookup = ChatLookupService(session_factory)
    saved_chat = await lookup.resolve(source.chat)

    if saved_chat is not None and saved_chat.is_blocked:
        _log.info(
            "repost_blocked_chat",
            chat_id=chat_id,
            source_chat_id=source.chat.id,
            source_chat_name=source.chat.title or "",
        )
        lines = [texts.REPOST_BLOCKED_CHAT]
        lines += await blocked_chat_lines(
            session_factory,
            block_reason=saved_chat.block_reason,
            blocked_by=saved_chat.blocked_by,
        )
        await temp_reply(message, "\n".join(lines))
        return

    author = source.from_user or User(id=0, is_bot=False, first_name="?")

    sig = build_signature(
        author=author,
        source_chat=source.chat,
        saved_chat=saved_chat,
        message_id_in_source=source.message_id,
    )

    # Determine what to publish once the category is chosen.
    file_id = extract_file_id(source)
    content_kind: str | None
    if source.media_group_id and len(media_group_cache.get(source.media_group_id) or []) >= 2:
        kind = "album"
        content_kind = "album"
    else:
        content_kind = classify_content(source)
        if content_kind is None:
            await temp_reply(message, unsupported_reply(source))
            return
        kind = "poll" if content_kind == "poll" else ("text" if content_kind == "text" else "media")

    await state.update_data(
        kind=kind,
        content_kind=content_kind,
        source_chat_id=source.chat.id,
        source_chat_name=source.chat.title or source.chat.username or str(source.chat.id),
        source_message_id=source.message_id,
        media_group_id=source.media_group_id,
        body_html=render_message_body(source),
        file_id=file_id,
        sig_text=sig.text,
        trigger_chat_id=chat_id,
        trigger_message_id=msg_id,
        requester_id=message.from_user.id if message.from_user else None,
        not_registered_hint=registration_hint(saved_chat),
    )

    # polls are forwarded (shared results), so no category is shown;
    # instead ask for a simple confirmation.
    if kind == "poll":
        await state.set_state(RepostState.waiting_for_poll_confirm)
        author_name = html_escape(author_display_name(author))
        await message.reply(
            texts.REPOST_POLL_CONFIRM.format(author=author_name),
            reply_markup=_poll_confirm_keyboard(),
        )
        return

    await state.set_state(RepostState.waiting_for_category)

    cats = await active_categories(session_factory)
    if not cats:
        await temp_reply(message, texts.REPOST_NO_CATEGORIES)
        await state.clear()
        return
    await message.reply(
        texts.REPOST_PICK_CATEGORY + registration_hint(saved_chat),
        reply_markup=category_keyboard(cats, scope="repost"),
    )


@router.callback_query(CategoryCallback.filter((F.action == "select") & (F.scope == "repost")))
async def repost_category_selected(
    query: CallbackQuery,
    callback_data: CategoryCallback,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    media_group_cache: MediaGroupCache,
) -> None:
    data = await state.get_data()
    if data.get("requester_id") != query.from_user.id:
        await safe_answer(query, texts.REPOST_ONLY_AUTHOR, show_alert=True)
        return

    kind = data.get("kind")
    if not kind:
        await safe_answer(query, texts.REPOST_STALE, show_alert=True)
        await state.clear()
        return

    category: str | None = None
    async with session_factory() as session:
        repo = CategoryRepository(session)
        cat = await repo.get_by_id(callback_data.category_id)
        category = cat.name if cat else None

    await state.clear()

    trigger_chat_id = data.get("trigger_chat_id")
    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")

    try:
        result, channel_message_ids = await _do_repost_publish(
            data, category, bot, settings, media_group_cache
        )
    except TelegramBadRequest as exc:
        _log.error("repost_publish_failed", chat_id=trigger_chat_id, error=str(exc))
        if isinstance(query.message, Message):
            await query.message.edit_text(
                texts.REPOST_PUBLISH_FAILED.format(error=html_escape(exc.message))
            )
        return

    # A pre-publish check (e.g. caption too long) returns an error with no ids.
    if not channel_message_ids:
        if isinstance(query.message, Message):
            await query.message.edit_text(result)
        return

    result += data.get("not_registered_hint") or ""

    await record_post(
        session_factory,
        author_id=query.from_user.id,
        author_name=author_display_name(query.from_user),
        source="mention",
        category=category or "",
        preview=make_preview(data.get("body_html")),
        source_chat_id=data.get("source_chat_id"),
        source_chat_name=data.get("source_chat_name") or "",
        channel_message_ids=channel_message_ids,
        source_message_id=data.get("source_message_id"),
        kind=data.get("content_kind") or "text",
        body_html=data.get("body_html") or "",
        file_id=data.get("file_id") or "",
        sig_text=data.get("sig_text") or "",
    )

    if isinstance(source_chat_id, int) and isinstance(source_message_id, int):
        await react_ok(bot, source_chat_id, source_message_id)
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(result)
            schedule_delete(query.message, ttl=60)
        except TelegramBadRequest:
            sent = await query.message.reply(result)
            schedule_delete(sent, ttl=60)
    _log.info(
        "repost_publish_done",
        chat_id=trigger_chat_id,
        kind=kind,
        category=category,
    )


@router.callback_query(CategoryCallback.filter((F.action == "cancel") & (F.scope == "repost")))
async def repost_category_cancel(query: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(query, texts.CANCELLED)
    await state.clear()
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(texts.CANCELLED)
        except TelegramBadRequest:
            pass


def _poll_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=texts.POLL_BTN_FORWARD,
                    callback_data=RepostPollCallback(action="forward").pack(),
                ),
                InlineKeyboardButton(
                    text=texts.CATEGORY_BTN_CANCEL,
                    callback_data=RepostPollCallback(action="cancel").pack(),
                ),
            ]
        ]
    )


@router.callback_query(RepostPollCallback.filter(F.action == "forward"))
async def repost_poll_forward(
    query: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    data = await state.get_data()
    if data.get("requester_id") != query.from_user.id:
        await safe_answer(query, texts.REPOST_ONLY_AUTHOR, show_alert=True)
        return

    source_chat_id = data.get("source_chat_id")
    source_message_id = data.get("source_message_id")
    if not isinstance(source_chat_id, int) or not isinstance(source_message_id, int):
        await safe_answer(query, texts.REPOST_STALE, show_alert=True)
        await state.clear()
        return

    await state.clear()

    try:
        sent = await bot.forward_message(
            chat_id=settings.main_channel_id,
            from_chat_id=source_chat_id,
            message_id=source_message_id,
            protect_content=settings.protect_content,
            message_thread_id=settings.main_channel_thread_id or None,
        )
    except TelegramBadRequest as exc:
        _log.error("repost_poll_forward_failed", error=str(exc))
        if isinstance(query.message, Message):
            await query.message.edit_text(
                texts.REPOST_PUBLISH_FAILED.format(error=html_escape(exc.message))
            )
        return

    await record_post(
        session_factory,
        author_id=query.from_user.id,
        author_name=author_display_name(query.from_user),
        source="mention",
        category="",
        preview=make_preview(data.get("body_html")),
        source_chat_id=source_chat_id,
        source_chat_name=data.get("source_chat_name") or "",
        channel_message_ids=str(sent.message_id),
        source_message_id=source_message_id,
        kind=data.get("content_kind") or "poll",
        body_html=data.get("body_html") or "",
        file_id=data.get("file_id") or "",
        sig_text=data.get("sig_text") or "",
    )

    result = texts.PUBLISHED_TEXT + (data.get("not_registered_hint") or "")
    await react_ok(bot, source_chat_id, source_message_id)
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(result)
            schedule_delete(query.message, ttl=60)
        except TelegramBadRequest:
            sent = await query.message.reply(result)
            schedule_delete(sent, ttl=60)
    _log.info("repost_poll_forwarded", chat_id=source_chat_id)


@router.callback_query(RepostPollCallback.filter(F.action == "cancel"))
async def repost_poll_cancel(query: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(query, texts.CANCELLED)
    await state.clear()
    if isinstance(query.message, Message):
        try:
            await query.message.edit_text(texts.CANCELLED)
        except TelegramBadRequest:
            pass


async def _do_repost_publish(
    data: dict[str, Any],
    category: str | None,
    bot: Bot,
    settings: Settings,
    media_group_cache: MediaGroupCache,
) -> tuple[str, str]:
    """Publish the stored repost context.

    Returns (completion message, comma-separated channel message ids).
    """
    kind = data.get("kind")
    body_html = data.get("body_html") or ""
    sig = PostSignature(text=data.get("sig_text") or "")
    caption = compose_html(body_html or None, sig.text, category)
    source_chat_id = data["source_chat_id"]
    source_message_id = data["source_message_id"]
    main = settings.main_channel_id

    # Pre-check the caption length so the user gets a friendly message instead
    # of a raw "message is too long" API error.
    if kind in ("text", "media", "album"):
        over = caption_over_limit(caption, is_text=(kind == "text"))
        if over is not None:
            return texts.POST_TOO_LONG.format(length=len(caption), limit=over), ""

    if kind == "text":
        sent = await bot.send_message(
            chat_id=main,
            text=caption,
            parse_mode="HTML",
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            protect_content=settings.protect_content,
            message_thread_id=settings.main_channel_thread_id or None,
        )
        return texts.PUBLISHED_TEXT, str(sent.message_id)

    if kind == "album":
        mgid = data.get("media_group_id")
        items = media_group_cache.get(mgid) if mgid else []
        if items and len(items) >= 2:
            sent_msgs = await publish_album(items, sig, bot, settings, category=category)
            return (
                texts.PUBLISHED_ALBUM.format(count=len(items)),
                ",".join(str(m.message_id) for m in sent_msgs),
            )
        # Fall back to single-item copy (cache miss after restart / TTL).
        copied = await bot.copy_message(
            chat_id=main,
            from_chat_id=source_chat_id,
            message_id=source_message_id,
            caption=caption,
            parse_mode="HTML",
            protect_content=settings.protect_content,
            message_thread_id=settings.main_channel_thread_id or None,
        )
        return texts.PUBLISHED_ALBUM_FALLBACK, str(copied.message_id)

    if kind == "poll":
        # polls are forwarded (shared results): no caption/signature
        forwarded = await bot.forward_message(
            chat_id=main,
            from_chat_id=source_chat_id,
            message_id=source_message_id,
            protect_content=settings.protect_content,
            message_thread_id=settings.main_channel_thread_id or None,
        )
        return texts.PUBLISHED_TEXT, str(forwarded.message_id)

    copied = await bot.copy_message(
        chat_id=main,
        from_chat_id=source_chat_id,
        message_id=source_message_id,
        caption=caption,
        parse_mode="HTML",
        protect_content=settings.protect_content,
        message_thread_id=settings.main_channel_thread_id or None,
    )
    return texts.PUBLISHED_TEXT, str(copied.message_id)
