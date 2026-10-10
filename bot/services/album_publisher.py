"""Publish a cached album (list of CachedMediaItem) to the main channel via
`bot.send_media_group`, with the signature as caption on the first item.

Shared by the repost handler (reply+mention in groups) and the wizard (PM).
"""

from __future__ import annotations

from typing import cast

from aiogram import Bot
from aiogram.types import InputMediaDocument, InputMediaPhoto, InputMediaVideo, Message

from bot.config import Settings
from bot.services.media_group_cache import CachedMediaItem
from bot.services.post_builder import PostSignature, compose_html


async def publish_album(
    items: list[CachedMediaItem],
    signature: PostSignature,
    bot: Bot,
    settings: Settings,
    *,
    category: str | None = None,
) -> list[Message]:
    """Send the album to the main channel with signature on the first item.

    Returns the sent messages so the caller can track their channel message ids.
    """
    # Telegram allows a caption on only one album item; use the first non-empty
    # body (usually the first item, but be defensive).
    body_html = next((i.body_html for i in items if i.body_html), "") or None
    full_caption = compose_html(body_html, signature.text, category)

    media: list[InputMediaPhoto | InputMediaVideo | InputMediaDocument] = []
    for idx, item in enumerate(items):
        caption = full_caption if idx == 0 else None
        parse_mode = "HTML" if idx == 0 else None
        if item.media_type == "photo":
            media.append(
                InputMediaPhoto(media=item.file_id, caption=caption, parse_mode=parse_mode)
            )
        elif item.media_type == "video":
            media.append(
                InputMediaVideo(media=item.file_id, caption=caption, parse_mode=parse_mode)
            )
        elif item.media_type == "document":
            media.append(
                InputMediaDocument(media=item.file_id, caption=caption, parse_mode=parse_mode)
            )

    sent = await bot.send_media_group(
        chat_id=settings.main_channel_id,
        media=cast(list, media),
        protect_content=settings.protect_content,
        message_thread_id=settings.main_channel_thread_id or None,
    )
    return list(sent)
