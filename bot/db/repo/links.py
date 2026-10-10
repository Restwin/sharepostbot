"""CommunityLinks repository: single-row table of community links."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import CommunityLinks
from bot.texts import LINK_LABEL_CHANNEL, LINK_LABEL_CHAT, LINK_LABEL_RULES

#: canonical key -> column attribute name.
LINK_FIELDS: dict[str, str] = {
    "rules": "rules_url",
    "channel": "channel_url",
    "chat": "main_chat_url",
}

_LINK_LABELS: dict[str, str] = {
    "rules": LINK_LABEL_RULES,
    "channel": LINK_LABEL_CHANNEL,
    "chat": LINK_LABEL_CHAT,
}


def link_label(key: str) -> str:
    return _LINK_LABELS.get(key, key)


class LinksRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> CommunityLinks:
        """Return the single row, creating it (id=1) on first access."""
        row = await self._session.get(CommunityLinks, 1)
        if row is None:
            row = CommunityLinks(id=1)
            self._session.add(row)
            await self._session.flush()
        return row

    async def set(self, key: str, url: str) -> CommunityLinks:
        field = LINK_FIELDS[key]
        row = await self.get()
        setattr(row, field, url)
        return row

    async def clear(self, key: str) -> CommunityLinks:
        field = LINK_FIELDS[key]
        row = await self.get()
        setattr(row, field, None)
        return row
