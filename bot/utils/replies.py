"""Shared reply helpers; lives in utils to avoid circular imports between handlers."""

from __future__ import annotations

import asyncio

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message, ReactionTypeEmoji

from bot import texts
from bot.logging_setup import get_logger

_log = get_logger("bot.replies")

# Keep references to background delete-tasks so they aren't garbage-collected.
_background_tasks: set[asyncio.Task[None]] = set()


async def react_ok(bot: Bot, chat_id: int, message_id: int) -> None:
    """Set a ✍️ reaction on a message, as a silent publication confirmation.

    Best-effort: swallows TelegramBadRequest (e.g. reactions disabled in chat).
    Callers that need a visible reply use `temp_reply`.
    """
    try:
        await bot.set_message_reaction(
            chat_id=chat_id,
            message_id=message_id,
            reaction=[ReactionTypeEmoji(emoji="✍️")],
        )
    except TelegramBadRequest:
        pass


async def notify_user(bot: Bot, user_id: int, text: str) -> None:
    """Send `text` to a user in PM; best-effort, errors are logged."""
    try:
        await bot.send_message(user_id, text)
    except TelegramBadRequest as exc:
        _log.warning("notify_user_failed", user_id=user_id, error=str(exc))


def schedule_delete(message: Message, ttl: int) -> None:
    """Schedule `message` for deletion after `ttl` seconds (fire-and-forget).

    The task is kept alive in `_background_tasks` so it isn't garbage-collected
    before it runs; delete failures are logged.
    """
    chat_id = message.chat.id

    async def _delete() -> None:
        await asyncio.sleep(ttl)
        try:
            await message.delete()
            _log.debug("temp_reply_deleted", chat_id=chat_id, message_id=message.message_id)
        except Exception as exc:
            _log.warning(
                "temp_reply_delete_failed",
                chat_id=chat_id,
                message_id=message.message_id,
                error=str(exc),
            )

    task = asyncio.create_task(_delete())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def temp_reply(message: Message, text: str, ttl: int = 60) -> Message:
    """Reply to a message; in group chats the reply auto-deletes after `ttl`
    seconds, in private chat it stays.
    """
    sent = await message.reply(text)
    if message.chat.type != ChatType.PRIVATE and ttl > 0:
        schedule_delete(sent, ttl)
    return sent


async def safe_answer(
    query: CallbackQuery, text: str | None = None, *, show_alert: bool = False
) -> None:
    """Answer a callback query, tolerating stale/expired queries.

    Telegram requires answering a callback query within ~1 minute. After a bot
    restart, queued callback updates may already be too old and
    `query.answer()` raises `TelegramBadRequest`; that specific case is logged
    and swallowed, other errors propagate.

    Alert text is truncated to 200 chars (Telegram limit for callback answers).
    For longer messages, use `send_long_answer()` instead.
    """
    try:
        safe_text = text
        if text and len(text) > 200:
            safe_text = text[:197] + "…"
        await query.answer(text=safe_text, show_alert=show_alert)
    except TelegramBadRequest as exc:
        msg = str(exc).lower()
        if "too old" in msg or "query id is invalid" in msg:
            from bot.logging_setup import get_logger

            get_logger("bot.callback").debug("stale_callback_query", error=str(exc))
            return
        raise


async def send_long_answer(
    query: CallbackQuery,
    text: str,
    *,
    disable_preview: bool = True,
    ttl: int = 0,
) -> None:
    """Answer callback with a short notification + send full text as a message.

    For text beyond Telegram's 200-char callback-alert limit. If `ttl` > 0,
    the message auto-deletes after that many seconds (for ephemeral
    instructions like "give me admin rights" that aren't useful long-term).
    """
    await safe_answer(query, texts.LONG_ANSWER_HINT)
    if query.message is not None:
        try:
            from aiogram.types import LinkPreviewOptions

            sent = await query.message.answer(
                text,
                link_preview_options=LinkPreviewOptions(is_disabled=disable_preview),
            )
        except TelegramBadRequest:
            return

        if ttl > 0:
            schedule_delete(sent, ttl)
