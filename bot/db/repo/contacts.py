"""AdminContact repository: public-facing admin directory shown via /contacts."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminContact


class AdminContactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_user_id(self, user_id: int) -> AdminContact | None:
        stmt = select(AdminContact).where(AdminContact.user_id == user_id)
        return await self._session.scalar(stmt)

    async def get_all(self) -> list[AdminContact]:
        """Return all contacts ordered by `display_order` then `id`."""
        stmt = select(AdminContact).order_by(AdminContact.display_order, AdminContact.id)
        result = await self._session.scalars(stmt)
        return list(result)

    async def upsert(
        self,
        *,
        user_id: int,
        public_role: str,
        comment: str = "",
        display_order: int = 100,
    ) -> AdminContact:
        existing = await self.get_by_user_id(user_id)
        if existing is None:
            contact = AdminContact(
                user_id=user_id,
                public_role=public_role,
                comment=comment,
                display_order=display_order,
            )
            self._session.add(contact)
            return contact
        existing.public_role = public_role
        existing.comment = comment
        existing.display_order = display_order
        return existing

    async def remove(self, user_id: int) -> None:
        await self._session.execute(delete(AdminContact).where(AdminContact.user_id == user_id))
