"""Record post statistics (best-effort, never breaks publishing)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.db.repo.stats import PostStatRepository
from bot.logging_setup import get_logger

_log = get_logger("bot.stats")


async def record_post(
    session_factory: async_sessionmaker[AsyncSession],
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
) -> None:
    """Persist one post-statistics row."""
    try:
        async with session_factory() as session:
            repo = PostStatRepository(session)
            await repo.add(
                author_id=author_id,
                author_name=author_name,
                source=source,
                category=category,
                preview=preview,
                source_chat_id=source_chat_id,
                source_chat_name=source_chat_name,
                channel_message_ids=channel_message_ids,
                source_message_id=source_message_id,
                kind=kind,
                body_html=body_html,
                file_id=file_id,
                sig_text=sig_text,
            )
            await session.commit()
    except Exception:
        _log.exception("stat_record_failed", author_id=author_id, source=source)
