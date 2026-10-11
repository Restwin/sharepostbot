"""Global update error handler.

aiogram routes exceptions that escaped handlers and middlewares here as
`ErrorEvent` (its ErrorsMiddleware wraps all outer middlewares). This is the
single place where update errors are logged: with update context and full
traceback, which the tech-chat sink forwards to admins when configured.
"""

from __future__ import annotations

from typing import Any

from aiogram import Dispatcher
from aiogram.types import ErrorEvent

from bot.logging_setup import get_logger

_log = get_logger("bot.errors")


def _context(event: ErrorEvent) -> dict[str, Any]:
    update = event.update
    context: dict[str, Any] = {
        "update_id": update.update_id,
        "update_type": update.event_type,
    }
    callback = update.callback_query
    if callback is not None:
        context["user_id"] = callback.from_user.id
    message = (
        update.message
        or update.edited_message
        or update.channel_post
        or update.edited_channel_post
        or (callback.message if callback else None)
    )
    if message is not None:
        context["chat_id"] = message.chat.id
        author = getattr(message, "from_user", None)
        if author is not None and "user_id" not in context:
            context["user_id"] = author.id
    return context


async def _handle_error(event: ErrorEvent) -> None:
    _log.error("update_handling_failed", exc_info=event.exception, **_context(event))


def register_error_handler(dp: Dispatcher) -> None:
    """Serve every unhandled update error from one logging handler."""
    dp.errors.register(_handle_error)
