"""PublishedPost repository (post statistics)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import PublishedPost


class PostStatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        author_id: int,
        author_name: str,
        source: str,
        category: str,
        preview: str,
        source_chat_id: int | None = None,
        source_chat_name: str = "",
        channel_message_ids: str = "",
        source_message_id: int | None = None,
        kind: str = "text",
        body_html: str = "",
        file_id: str = "",
        sig_text: str = "",
    ) -> PublishedPost:
        post = PublishedPost(
            author_id=author_id,
            author_name=author_name,
            source=source,
            source_chat_id=source_chat_id,
            source_chat_name=source_chat_name,
            category=category,
            preview=preview,
            channel_message_ids=channel_message_ids,
            source_message_id=source_message_id,
            kind=kind,
            body_html=body_html,
            file_id=file_id,
            sig_text=sig_text,
        )
        self._session.add(post)
        return post

    async def get_by_id(self, post_id: int) -> PublishedPost | None:
        return await self._session.get(PublishedPost, post_id)

    async def get_recent(self, limit: int = 10) -> list[PublishedPost]:
        stmt = (
            select(PublishedPost)
            .where(PublishedPost.is_deleted.is_(False))
            .order_by(PublishedPost.id.desc())
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return list(result)

    async def count(self) -> int:
        stmt = (
            select(func.count())
            .select_from(PublishedPost)
            .where(PublishedPost.is_deleted.is_(False))
        )
        return await self._session.scalar(stmt) or 0

    async def get_by_author(self, author_id: int, limit: int = 10) -> list[PublishedPost]:
        stmt = (
            select(PublishedPost)
            .where(PublishedPost.author_id == author_id, PublishedPost.is_deleted.is_(False))
            .order_by(PublishedPost.id.desc())
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return list(result)

    async def count_by_author(self, author_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(PublishedPost)
            .where(PublishedPost.author_id == author_id, PublishedPost.is_deleted.is_(False))
        )
        return await self._session.scalar(stmt) or 0

    async def count_by_category(self) -> list[tuple[str, int]]:
        stmt = (
            select(PublishedPost.category, func.count())
            .where(PublishedPost.is_deleted.is_(False))
            .group_by(PublishedPost.category)
            .order_by(func.count().desc(), PublishedPost.category)
        )
        result = await self._session.execute(stmt)
        return [(row[0], row[1]) for row in result]

    async def count_by_user(self) -> list[tuple[int, str, int]]:
        stmt = (
            select(PublishedPost.author_id, PublishedPost.author_name, func.count())
            .where(PublishedPost.is_deleted.is_(False))
            .group_by(PublishedPost.author_id, PublishedPost.author_name)
            .order_by(func.count().desc(), PublishedPost.author_name)
        )
        result = await self._session.execute(stmt)
        return [(row[0], row[1], row[2]) for row in result]

    def mark_deleted(self, post: PublishedPost) -> None:
        post.is_deleted = True

    def update_source_content(
        self,
        post: PublishedPost,
        *,
        body_html: str,
        file_id: str = "",
        media_changed: bool = False,
    ) -> None:
        """Refresh the source snapshot after an edit."""
        post.body_html = body_html
        post.file_id = file_id
        post.source_edited = True
        if media_changed:
            post.source_media_changed = True

    def clear_source_edited(self, post: PublishedPost) -> None:
        post.source_edited = False
        post.source_media_changed = False

    async def get_by_source(self, chat_id: int, message_id: int) -> list[PublishedPost]:
        """Find live posts whose source is the given (chat_id, message_id)."""
        stmt = select(PublishedPost).where(
            PublishedPost.source_chat_id == chat_id,
            PublishedPost.source_message_id == message_id,
            PublishedPost.is_deleted.is_(False),
        )
        result = await self._session.scalars(stmt)
        return list(result)
