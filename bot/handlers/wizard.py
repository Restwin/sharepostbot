"""FSM wizard for posting via PM.

Flow: /post (or the menu button) → waiting_for_publish → user sends content →
category → confirm → the post goes to the main channel.

Albums arrive as separate updates sharing one media_group_id; items are held in
MediaGroupCache (TTL 1 hour), not in FSM state, and one confirm is shown after
a 2s debounce. _album_confirmed/_album_finished guard against redelivered
updates and duplicate confirms.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InaccessibleMessage,
    LinkPreviewOptions,
    Message,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import texts
from bot.config import Settings
from bot.db.repo.categories import CategoryRepository
from bot.logging_setup import get_logger
from bot.services.album_publisher import publish_album
from bot.services.categories import active_categories
from bot.services.content_types import NON_ANONYMOUS_POLL_REPLY, UNSUPPORTED_REPLY
from bot.services.media_group_cache import MediaGroupCache
from bot.services.post_builder import (
    author_display_name,
    build_signature,
    caption_over_limit,
    compose_html,
    render_message_body,
)
from bot.services.post_stats import record_post
from bot.utils.callbacks import CategoryCallback, WizardCallback, category_keyboard
from bot.utils.formatting import html_escape, make_preview
from bot.utils.replies import safe_answer

router = Router(name="wizard")
_log = get_logger("bot.wizard")


class WizardState(StatesGroup):
    waiting_for_publish = State()


WIZARD_TEXT = texts.WIZARD_INTRO

# Debounce timers for album collection, keyed by chat_id. Each new album item
# cancels the previous timer and starts a fresh 2s countdown; when it finally
# fires, we show ONE confirm button for the whole album.
_pending_album_checks: dict[int, asyncio.Task[None]] = {}

# Albums that already got a confirm message, to suppress duplicate confirms
# from a late debounce timer or redelivered updates. Keyed by
# (chat_id, media_group_id); cleared only when a new album starts in the chat.
_album_confirmed: set[tuple[int, str]] = set()

# Albums that were published or cancelled; redelivered items for these are
# dropped silently. Same key; cleaned on a new album or bot restart.
_album_finished: set[tuple[int, str]] = set()

# Timestamps for the above sets — entries older than _GUARD_TTL are purged.
# Without this, long-running bots accumulate stale entries forever.
_album_confirmed_ts: dict[tuple[int, str], float] = {}
_album_finished_ts: dict[tuple[int, str], float] = {}
_GUARD_TTL_SECONDS: int = 3600  # 1 hour — matches MediaGroupCache TTL


def _purge_stale_guards() -> None:
    """Drop _album_confirmed / _album_finished entries older than _GUARD_TTL.

    Called on every new album start; cheap because sets are small per chat.
    """
    import time

    now = time.monotonic()
    for store, ts_store in (
        (_album_confirmed, _album_confirmed_ts),
        (_album_finished, _album_finished_ts),
    ):
        stale = {k for k, ts in ts_store.items() if now - ts > _GUARD_TTL_SECONDS}
        if stale:
            store.difference_update(stale)
            for k in stale:
                ts_store.pop(k, None)


@router.message(
    Command("cancel"), StateFilter(WizardState.waiting_for_publish), F.chat.type == ChatType.PRIVATE
)
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    _log.info("wizard_cancel", chat_id=message.chat.id)
    await state.clear()
    await message.reply(texts.WIZARD_CANCELLED)


@router.message(Command("post"), F.chat.type == ChatType.PRIVATE)
async def cmd_post(message: Message, state: FSMContext) -> None:
    _log.info(
        "wizard_start",
        chat_id=message.chat.id,
        user_id=message.from_user.id if message.from_user else None,
    )
    await state.set_state(WizardState.waiting_for_publish)
    await message.reply(WIZARD_TEXT)


@router.callback_query(WizardCallback.filter(F.action == "start"))
async def callback_start(query: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(query)
    if query.message is None:
        await safe_answer(query, texts.WIZARD_CANT_OPEN, show_alert=True)
        return
    if query.message.chat.type != ChatType.PRIVATE:
        await safe_answer(query, texts.WIZARD_PM_ONLY, show_alert=True)
        return
    _log.info("wizard_start", chat_id=query.message.chat.id, via="callback")
    await state.set_state(WizardState.waiting_for_publish)
    await query.message.answer(WIZARD_TEXT)


@router.message(WizardState.waiting_for_publish, F.chat.type == ChatType.PRIVATE)
async def accept_content(
    message: Message,
    state: FSMContext,
    bot: Bot,
    media_group_cache: MediaGroupCache,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if message.text and message.text.startswith("/"):
        return  # let other command handlers process it

    # ─── Album (media group) ───
    if message.media_group_id:
        await _accept_album_item(message, state, bot, media_group_cache, session_factory)
        return

    # ─── Single item ───
    payload: dict[str, Any] = {
        "source_chat_id": message.chat.id,
        "source_message_id": message.message_id,
    }

    if message.text is not None:
        payload["kind"] = "text"
        payload["body_html"] = message.html_text
        _log.info("wizard_content", chat_id=message.chat.id, kind="text", length=len(message.text))
    elif message.photo:
        largest = max(message.photo, key=lambda p: p.file_size or 0)
        payload["kind"] = "photo"
        payload["file_id"] = largest.file_id
        payload["body_html"] = render_message_body(message)
        _log.info("wizard_content", chat_id=message.chat.id, kind="photo")
    elif message.video:
        payload["kind"] = "video"
        payload["file_id"] = message.video.file_id
        payload["body_html"] = render_message_body(message)
        _log.info("wizard_content", chat_id=message.chat.id, kind="video")
    elif message.document:
        payload["kind"] = "document"
        payload["file_id"] = message.document.file_id
        payload["body_html"] = render_message_body(message)
        _log.info("wizard_content", chat_id=message.chat.id, kind="document")
    elif message.poll is not None:
        if not message.poll.is_anonymous:
            await message.reply(NON_ANONYMOUS_POLL_REPLY)
            return
        payload["kind"] = "poll"
        payload["poll_question"] = message.poll.question
        payload["poll_options"] = [o.text for o in message.poll.options]
        payload["poll_type"] = message.poll.type
        payload["poll_is_anonymous"] = message.poll.is_anonymous
        payload["poll_allows_multiple"] = message.poll.allows_multiple_answers
        payload["poll_correct_option_id"] = message.poll.correct_option_id
        payload["poll_explanation"] = message.poll.explanation
        _log.info("wizard_content", chat_id=message.chat.id, kind="poll")
    else:
        await message.reply(UNSUPPORTED_REPLY)
        return

    await state.update_data(payload)

    cats = await active_categories(session_factory)
    if not cats:
        await message.reply(texts.WIZARD_NO_CATEGORIES)
        await state.clear()
        return
    await message.reply(
        texts.WIZARD_PICK_CATEGORY,
        reply_markup=category_keyboard(cats, scope="wizard"),
    )


async def _accept_album_item(
    message: Message,
    state: FSMContext,
    bot: Bot,
    media_group_cache: MediaGroupCache,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Collect album items via MediaGroupCache; show ONE confirm after 2s debounce.

    Redelivery-safe: if (chat_id, mgid) is already in _album_finished (published
    or cancelled) or _album_confirmed (confirm already shown), silently ignore.
    """
    mgid = message.media_group_id
    assert mgid is not None  # checked by caller
    chat_id = message.chat.id
    key = (chat_id, mgid)

    # Redelivery after publish/cancel → drop silently.
    if key in _album_finished:
        _log.info(
            "album_redelivery_ignored",
            chat_id=chat_id,
            media_group_id=mgid,
            message_id=message.message_id,
        )
        return

    data = await state.get_data()
    is_new_album = data.get("kind") != "album" or data.get("media_group_id") != mgid

    if is_new_album:
        # New album (or first after publish): clear per-chat guards so the new
        # album can be collected and confirmed. Also purge stale entries past TTL.
        _cleanup_album_state(chat_id)
        _purge_stale_guards()
        collecting_msg = await message.reply(texts.WIZARD_COLLECTING)
        await state.update_data(
            kind="album",
            media_group_id=mgid,
            source_chat_id=chat_id,
            collecting_message_id=collecting_msg.message_id,
        )
        _log.info(
            "album_started",
            chat_id=chat_id,
            media_group_id=mgid,
            first_message_id=message.message_id,
        )

    _schedule_album_done(chat_id, mgid, state, bot, media_group_cache, session_factory)


def _schedule_album_done(
    chat_id: int,
    mgid: str,
    state: FSMContext,
    bot: Bot,
    cache: MediaGroupCache,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """(Re)arm the 2s debounce timer for this chat. Only the last one fires."""
    old = _pending_album_checks.get(chat_id)
    if old is not None and not old.done():
        old.cancel()

    async def _check() -> None:
        try:
            await asyncio.sleep(2)
        except asyncio.CancelledError:
            return

        # state.get_state() returns a string; compare with != against the State
        # (an `is` check would always fail and trip the guard)
        current_state = await state.get_state()
        if current_state != WizardState.waiting_for_publish:
            return

        current = await state.get_data()
        if current.get("kind") != "album" or current.get("media_group_id") != mgid:
            return  # state changed (new album started)

        # Guard: don't send a second confirm for the same album.
        key = (chat_id, mgid)
        if key in _album_confirmed or key in _album_finished:
            return
        import time

        _album_confirmed.add(key)
        _album_confirmed_ts[key] = time.monotonic()

        items = cache.get(mgid)
        if not items:
            return

        # Delete the "📸 Собираю альбом..." placeholder before showing confirm.
        collecting_id = current.get("collecting_message_id")
        if collecting_id is not None:
            try:
                await bot.delete_message(chat_id, collecting_id)
            except TelegramBadRequest:
                pass  # already deleted or too old — not critical

        _log.info("album_ready", chat_id=chat_id, media_group_id=mgid, item_count=len(items))

        cats = await active_categories(session_factory)
        if not cats:
            await bot.send_message(chat_id, texts.WIZARD_NO_CATEGORIES)
            return
        await bot.send_message(
            chat_id,
            texts.WIZARD_ALBUM_READY.format(count=len(items)),
            reply_markup=category_keyboard(cats, scope="wizard"),
        )

    task = asyncio.create_task(_check())
    _pending_album_checks[chat_id] = task
    task.add_done_callback(lambda t: _pending_album_checks.pop(chat_id, None))


@router.callback_query(CategoryCallback.filter((F.action == "select") & (F.scope == "wizard")))
async def wizard_category_selected(
    query: CallbackQuery,
    callback_data: CategoryCallback,
    state: FSMContext,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await safe_answer(query)

    async with session_factory() as session:
        repo = CategoryRepository(session)
        category = await repo.get_by_id(callback_data.category_id)

    if category is None:
        await state.clear()
        if isinstance(query.message, Message):
            await query.message.edit_text(texts.WIZARD_CATEGORY_NOT_FOUND)
        return

    await state.update_data(category=category.name)

    builder = InlineKeyboardBuilder()
    builder.button(text=texts.WIZARD_BTN_PUBLISH, callback_data=WizardCallback(action="publish"))
    builder.button(text=texts.WIZARD_BTN_CANCEL, callback_data=WizardCallback(action="cancel"))
    if isinstance(query.message, Message):
        await query.message.edit_text(
            texts.WIZARD_CONFIRM.format(category=html_escape(category.name)),
            reply_markup=builder.as_markup(),
        )
    _log.info("wizard_category_selected", chat_id=query.from_user.id, category=category.name)


@router.callback_query(CategoryCallback.filter((F.action == "cancel") & (F.scope == "wizard")))
async def wizard_category_cancel(query: CallbackQuery, state: FSMContext) -> None:
    await callback_cancel(query, state)


@router.callback_query(WizardCallback.filter(F.action == "publish"))
async def callback_publish(
    query: CallbackQuery,
    state: FSMContext,
    bot: Bot,
    settings: Settings,
    media_group_cache: MediaGroupCache,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await safe_answer(query)

    chat_id = query.message.chat.id if query.message else query.from_user.id
    _cancel_pending_album_check(chat_id)

    # state.get_state() returns a string; `is not` would always fail and
    # block every publish.
    current_state = await state.get_state()
    if current_state != WizardState.waiting_for_publish:
        _log.info("wizard_publish_stale", chat_id=chat_id, reason="state_cleared")
        if query.message is not None:
            await _strip_keyboard(query.message)
            await query.message.answer(texts.WIZARD_SESSION_STALE)
        await state.clear()
        return

    data = await state.get_data()
    kind: str | None = data.get("kind")
    body_html: str | None = data.get("body_html")
    category: str | None = data.get("category")

    if not kind or query.message is None:
        await state.clear()
        return

    # Mark album as finished BEFORE publishing so redelivered items are ignored
    # even if publish takes a moment.
    mgid = data.get("media_group_id")
    if kind == "album" and mgid:
        import time

        finished_key = (chat_id, mgid)
        _album_finished.add(finished_key)
        _album_finished_ts[finished_key] = time.monotonic()

    from aiogram.types import Chat

    author = query.from_user
    sig = build_signature(
        author=author,
        source_chat=Chat(id=query.message.chat.id, type="private", first_name=author.first_name),
        saved_chat=None,
        message_id_in_source=None,
    )

    _log.info("wizard_publish", chat_id=chat_id, kind=kind, media_group_id=mgid)

    # Pre-check the caption length so the user gets a friendly message instead
    # of a raw "message is too long" API error.
    if kind in ("text", "photo", "video", "document"):
        full_caption = compose_html(body_html, sig.text, category)
        over = caption_over_limit(full_caption, is_text=(kind == "text"))
        if over is not None:
            await query.message.answer(
                texts.POST_TOO_LONG.format(length=len(full_caption), limit=over)
            )
            await state.clear()
            return

    channel_message_ids = ""
    try:
        if kind == "text":
            full_text = compose_html(body_html, sig.text, category)
            sent = await bot.send_message(
                chat_id=settings.main_channel_id,
                text=full_text,
                parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                protect_content=settings.protect_content,
                message_thread_id=settings.main_channel_thread_id or None,
            )
            channel_message_ids = str(sent.message_id)
        elif kind == "photo":
            full_caption = compose_html(body_html, sig.text, category)
            sent = await bot.send_photo(
                chat_id=settings.main_channel_id,
                photo=data["file_id"],
                caption=full_caption,
                parse_mode="HTML",
                protect_content=settings.protect_content,
                message_thread_id=settings.main_channel_thread_id or None,
            )
            channel_message_ids = str(sent.message_id)
        elif kind == "video":
            full_caption = compose_html(body_html, sig.text, category)
            sent = await bot.send_video(
                chat_id=settings.main_channel_id,
                video=data["file_id"],
                caption=full_caption,
                parse_mode="HTML",
                protect_content=settings.protect_content,
                message_thread_id=settings.main_channel_thread_id or None,
            )
            channel_message_ids = str(sent.message_id)
        elif kind == "document":
            full_caption = compose_html(body_html, sig.text, category)
            sent = await bot.send_document(
                chat_id=settings.main_channel_id,
                document=data["file_id"],
                caption=full_caption,
                parse_mode="HTML",
                protect_content=settings.protect_content,
                message_thread_id=settings.main_channel_thread_id or None,
            )
            channel_message_ids = str(sent.message_id)
        elif kind == "poll":
            # Polls have no caption, so the signature can't be attached here.
            sent = await bot.send_poll(
                chat_id=settings.main_channel_id,
                question=data["poll_question"],
                options=data["poll_options"],
                type=data["poll_type"],
                is_anonymous=data["poll_is_anonymous"],
                allows_multiple_answers=data["poll_allows_multiple"],
                correct_option_id=data["poll_correct_option_id"],
                explanation=data["poll_explanation"],
                protect_content=settings.protect_content,
                message_thread_id=settings.main_channel_thread_id or None,
            )
            channel_message_ids = str(sent.message_id)
        elif kind == "album":
            if not mgid:
                await query.message.answer(texts.WIZARD_SESSION_STALE)
                await state.clear()
                return
            items = media_group_cache.get(mgid)
            if not items:
                await query.message.answer(texts.WIZARD_ALBUM_STALE)
                await state.clear()
                return
            sent_msgs = await publish_album(items, sig, bot, settings, category=category)
            channel_message_ids = ",".join(str(m.message_id) for m in sent_msgs)
        else:
            await query.message.answer(texts.WIZARD_UNKNOWN_KIND)
            await state.clear()
            return
    except TelegramBadRequest as exc:
        _log.error("wizard_publish_failed", chat_id=chat_id, error=str(exc))
        await query.message.answer(
            texts.WIZARD_PUBLISH_FAILED.format(error=html_escape(exc.message))
        )
        await state.clear()
        return
    except Exception as exc:
        _log.exception("wizard_publish_failed", chat_id=chat_id, error=str(exc))
        await query.message.answer(texts.WIZARD_INTERNAL_ERROR.format(error=html_escape(str(exc))))
        await state.clear()
        return

    await record_post(
        session_factory,
        author_id=query.from_user.id,
        author_name=author_display_name(query.from_user),
        source="pm",
        category=category or "",
        preview=make_preview(body_html),
        source_chat_id=data.get("source_chat_id"),
        source_message_id=data.get("source_message_id"),
        channel_message_ids=channel_message_ids,
        kind=kind or "text",
        body_html=body_html or "",
        file_id=data.get("file_id") or "",
        sig_text=sig.text,
    )

    await state.clear()
    await _strip_keyboard(query.message)
    await query.message.answer(texts.WIZARD_PUBLISHED)
    _log.info("wizard_publish_done", chat_id=chat_id, kind=kind)


@router.callback_query(WizardCallback.filter(F.action == "cancel"))
async def callback_cancel(query: CallbackQuery, state: FSMContext) -> None:
    await safe_answer(query, texts.WIZARD_CANCELLED)

    chat_id = query.message.chat.id if query.message else query.from_user.id
    _cancel_pending_album_check(chat_id)

    # Mark current album as finished so redelivered items are ignored.
    data = await state.get_data()
    mgid = data.get("media_group_id")
    if mgid:
        import time

        finished_key = (chat_id, mgid)
        _album_finished.add(finished_key)
        _album_finished_ts[finished_key] = time.monotonic()

    await state.clear()
    if query.message is not None:
        await _strip_keyboard(query.message)
        await query.message.answer(texts.WIZARD_CANCELLED)
    _log.info("wizard_cancel", chat_id=chat_id, media_group_id=mgid)


def _cancel_pending_album_check(chat_id: int) -> None:
    task = _pending_album_checks.pop(chat_id, None)
    if task is not None and not task.done():
        task.cancel()


def _cleanup_album_state(chat_id: int) -> None:
    """Clear per-chat album guards when a NEW album starts.

    Removes _album_confirmed and _album_finished entries for this chat so the
    new album can be collected and confirmed. NOT called on publish/cancel —
    redelivered items for a finished album must stay ignored.
    """
    for s in (_album_confirmed, _album_finished):
        keys_to_remove = {k for k in s if k[0] == chat_id}
        s.difference_update(keys_to_remove)


async def _strip_keyboard(message: Message | InaccessibleMessage) -> None:
    """Remove inline keyboard from a message (best-effort, ignore errors)."""
    if not isinstance(message, Message):
        return
    try:
        await message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass  # message too old or already edited — not critical
