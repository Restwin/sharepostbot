"""SavedChat repository: lookup by chat_id (primary) or exact_name."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import SavedChat


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_chat_id(self, chat_id: int) -> SavedChat | None:
        stmt = select(SavedChat).where(SavedChat.chat_id == chat_id)
        return await self._session.scalar(stmt)

    async def get_by_name(self, exact_name: str) -> SavedChat | None:
        stmt = select(SavedChat).where(SavedChat.exact_name == exact_name)
        return await self._session.scalar(stmt)

    async def get_by_name_all(self, exact_name: str) -> list[SavedChat]:
        """All chats with this exact name (usually 0 or 1, but names can repeat)."""
        stmt = select(SavedChat).where(SavedChat.exact_name == exact_name)
        result = await self._session.scalars(stmt)
        return list(result)

    async def get_all(self) -> list[SavedChat]:
        stmt = select(SavedChat).order_by(SavedChat.exact_name)
        result = await self._session.scalars(stmt)
        return list(result)

    async def get_page(self, offset: int, limit: int) -> list[SavedChat]:
        stmt = select(SavedChat).order_by(SavedChat.exact_name).offset(offset).limit(limit)
        result = await self._session.scalars(stmt)
        return list(result)

    async def count(self) -> int:
        stmt = select(func.count()).select_from(SavedChat)
        return (await self._session.scalar(stmt)) or 0

    async def get_by_added_by(self, user_id: int) -> list[SavedChat]:
        stmt = select(SavedChat).where(SavedChat.added_by == user_id).order_by(SavedChat.exact_name)
        result = await self._session.scalars(stmt)
        return list(result)

    async def get_by_added_by_page(self, user_id: int, offset: int, limit: int) -> list[SavedChat]:
        stmt = (
            select(SavedChat)
            .where(SavedChat.added_by == user_id)
            .order_by(SavedChat.exact_name)
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return list(result)

    async def count_by_added_by(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(SavedChat).where(SavedChat.added_by == user_id)
        return (await self._session.scalar(stmt)) or 0

    async def remove_by_name(self, exact_name: str) -> bool:
        """Delete every chat with this exact name. True when something was deleted."""
        result = await self._session.execute(
            delete(SavedChat).where(SavedChat.exact_name == exact_name)
        )
        return (getattr(result, "rowcount", 0) or 0) > 0

    async def remove_by_chat_id(self, chat_id: int) -> bool:
        result = await self._session.execute(delete(SavedChat).where(SavedChat.chat_id == chat_id))
        return (getattr(result, "rowcount", 0) or 0) > 0

    async def set_blocked(
        self,
        exact_name: str,
        blocked: bool,
        *,
        block_reason: str = "",
        blocked_by: int | None = None,
    ) -> SavedChat | None:
        """Mark a chat blocked/unblocked by exact name. Returns None if not found.

        `block_reason` and `blocked_by` only apply when `blocked` is True;
        otherwise they are cleared (symmetric with UserRepository.set_role).
        """
        chat = await self.get_by_name(exact_name)
        if chat is None:
            return None
        chat.is_blocked = blocked
        if blocked:
            chat.block_reason = block_reason
            chat.blocked_by = blocked_by
        else:
            chat.block_reason = ""
            chat.blocked_by = None
        return chat

    async def add_or_update(
        self,
        *,
        chat_id: int,
        exact_name: str,
        join_link: str,
        added_by: int | None = None,
        link_source: str = "bot",
        join_approval: str = "open",
    ) -> bool:
        """Return True if updated, False if inserted.

        `added_by` is set on insert; on update it only fills a missing value
        (never overwrites the original registrar). `link_source` and
        `join_approval` are always set.
        """
        existing = await self.get_by_chat_id(chat_id)
        if existing is None:
            chat = SavedChat(
                chat_id=chat_id,
                exact_name=exact_name,
                join_link=join_link,
                link_source=link_source,
                join_approval=join_approval,
                added_by=added_by,
            )
            self._session.add(chat)
            return False
        existing.chat_id = chat_id
        existing.exact_name = exact_name
        existing.join_link = join_link
        existing.link_source = link_source
        existing.join_approval = join_approval
        if existing.added_by is None and added_by is not None:
            existing.added_by = added_by
        return True
