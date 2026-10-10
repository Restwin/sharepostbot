"""Content-type whitelist for republishing.

Publishable: text, photos (including albums), videos, documents, anonymous
polls. Everything else (stickers, geo, contacts, voice/video messages, music,
GIFs, dice, non-anonymous polls, task lists) is rejected.

Task lists and non-anonymous polls cannot be republished: the Bot API has no
way to copy or send them into a channel.
"""

from __future__ import annotations

from aiogram.types import Message

from bot.texts import NON_ANONYMOUS_POLL, UNSUPPORTED_CONTENT

UNSUPPORTED_REPLY = UNSUPPORTED_CONTENT
NON_ANONYMOUS_POLL_REPLY = NON_ANONYMOUS_POLL


def classify_content(message: Message) -> str | None:
    """Return the supported content kind for a message, or None if unsupported.

    Kinds: "text", "photo", "video", "document", "poll" (anonymous polls only).
    """
    if message.poll is not None:
        return "poll" if message.poll.is_anonymous else None
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.document:
        return "document"
    if message.text is not None:
        return "text"
    return None


def unsupported_reply(message: Message) -> str:
    """Human-readable reject reason for an unsupported message."""
    if message.poll is not None and not message.poll.is_anonymous:
        return NON_ANONYMOUS_POLL_REPLY
    return UNSUPPORTED_REPLY


def extract_file_id(message: Message) -> str:
    """Return the media file_id for a photo/video/document message, else ""."""
    if message.photo:
        return max(message.photo, key=lambda p: p.file_size or 0).file_id
    if message.video:
        return message.video.file_id
    if message.document:
        return message.document.file_id
    return ""
