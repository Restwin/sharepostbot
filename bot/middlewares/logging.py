"""Logging middleware: structured per-update logs with secret scrubbing.

Logs rich details per update: update_id, type, chat_id, user, content_type,
media_group_id, command name, text preview (first 60 chars), reply target,
callback data. Controlled by LOG_LEVEL in config.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject, Update

from bot.logging_setup import get_logger


def _content_type(msg: Message) -> str | None:
    # `Message.content_type` is a property in aiogram that returns the canonical
    # type string. Use it instead of an exhaustive hand-rolled ladder so we
    # automatically pick up new types.
    try:
        return msg.content_type
    except Exception:
        return None


def _command_name(msg: Message) -> str | None:
    if not msg.text or not msg.text.startswith("/"):
        return None
    for ent in msg.entities or []:
        if ent.type == "bot_command":
            return msg.text[ent.offset : ent.offset + ent.length].lstrip("/").split("@")[0]
    return None


def _text_preview(msg: Message) -> str | None:
    text = msg.text or msg.caption
    if not text:
        return None
    text = text.replace("\n", " ").strip()
    return text[:60] + ("…" if len(text) > 60 else "")


class LoggingMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._log = get_logger("bot.update")

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)

        msg = event.message or (event.callback_query.message if event.callback_query else None)
        chat_id = msg.chat.id if msg else None
        chat_type = msg.chat.type if msg else None
        chat_title = msg.chat.title if msg and msg.chat.title else None

        user = (
            getattr(event.callback_query, "from_user", None)
            if event.callback_query
            else (event.message.from_user if event.message else None)
        )
        user_id = user.id if user else None
        username = user.username if user else None
        first_name = user.first_name if user else None

        fields: dict[str, Any] = {
            "update_id": event.update_id,
            "update_type": event.event_type,
            "chat_id": chat_id,
            "chat_type": chat_type,
            "user_id": user_id,
            "username": username,
        }
        if chat_title:
            fields["chat_title"] = chat_title
        if first_name:
            fields["first_name"] = first_name

        if event.message is not None:
            fields["content_type"] = _content_type(event.message)
            fields["message_id"] = event.message.message_id
            if event.message.media_group_id:
                fields["media_group_id"] = event.message.media_group_id
            cmd = _command_name(event.message)
            if cmd:
                fields["command"] = cmd
            preview = _text_preview(event.message)
            if preview:
                fields["preview"] = preview
            if event.message.reply_to_message:
                fields["reply_to"] = event.message.reply_to_message.message_id

        if event.callback_query is not None:
            cq = event.callback_query
            fields["callback_id"] = cq.id
            if cq.data:
                fields["callback_data"] = cq.data[:60]
            fields["callback_message_id"] = cq.message.message_id if cq.message else None

        self._log.debug("update", **fields)
        try:
            return await handler(event, data)
        except Exception as exc:
            self._log.exception(
                "handler_error",
                update_id=event.update_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise
