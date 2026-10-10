"""Resolve a source Chat to a SavedChat record.

Keyed by `chat_id` (numeric, immutable); titles change at any time, so a
mismatch is treated as a rename.

Rename fallback: when `chat.title` differs from `saved.exact_name`, update the
DB record in place and return the updated object. Catches renames the
service-message handler missed (bot offline >24h, lost service message). The
check runs only when a SavedChat is needed, so no in-memory cache is required.
"""

from __future__ import annotations

from aiogram.types import Chat
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.db.models import SavedChat
from bot.db.repo.chats import ChatRepository
from bot.logging_setup import get_logger

_log = get_logger("bot.chat_lookup")


class ChatLookupService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def resolve(self, chat: Chat) -> SavedChat | None:
        async with self._session_factory() as session:
            repo = ChatRepository(session)
            saved = await repo.get_by_chat_id(chat.id)

            # rename fallback: telegram title is newer than the stored one
            if saved is not None and chat.title and saved.exact_name != chat.title:
                _log.info(
                    "chat_renamed_lookup_fallback",
                    chat_id=chat.id,
                    old_name=saved.exact_name,
                    new_name=chat.title,
                )
                saved.exact_name = chat.title
                await session.commit()

            return saved
