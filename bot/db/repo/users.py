"""AppUser repository with role-based access helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AppUser, RestrictMode, UserRole


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: int) -> AppUser | None:
        return await self._session.get(AppUser, user_id)

    async def get_by_username(self, username: str) -> AppUser | None:
        stmt = select(AppUser).where(func.lower(AppUser.username) == username.lower())
        return await self._session.scalar(stmt)

    async def exists(self, user_id: int) -> bool:
        return await self.get(user_id) is not None

    async def get_all(self) -> list[AppUser]:
        stmt = select(AppUser).order_by(AppUser.joined)
        result = await self._session.scalars(stmt)
        return list(result)

    async def get_page(self, offset: int, limit: int) -> list[AppUser]:
        """One page of users, most recently active first.

        `last_activity` desc with `id` desc as a tiebreaker; users whose
        `last_activity` is NULL (rows predating the column) sort last in SQLite.
        """
        stmt = (
            select(AppUser)
            .order_by(AppUser.last_activity.desc(), AppUser.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.scalars(stmt)
        return list(result)

    async def count(self) -> int:
        stmt = select(func.count()).select_from(AppUser)
        return (await self._session.scalar(stmt)) or 0

    async def add(self, user: AppUser) -> None:
        self._session.add(user)

    async def update(self, user: AppUser) -> None:
        await self._session.merge(user)

    async def upsert(self, user: AppUser) -> None:
        existing = await self.get(user.id)
        if existing is None:
            await self.add(user)
        else:
            await self.update(user)

    # --- Role helpers ---

    async def get_role(self, user_id: int) -> UserRole:
        user = await self.get(user_id)
        return user.role if user is not None else UserRole.UNKNOWN

    async def set_role(
        self,
        user_id: int,
        role: UserRole,
        *,
        block_reason: str = "",
        restrict_mode: RestrictMode = RestrictMode.BOTH,
        blocked_by: int | None = None,
    ) -> AppUser:
        """Set the role on a user, creating the row if missing.

        `block_reason`, `restrict_mode` and `blocked_by` only apply when
        role == BLOCKED; otherwise they are cleared.
        """
        user = await self.get(user_id)
        if user is None:
            user = AppUser(id=user_id, role=role)
            self._session.add(user)
        user.role = role
        if role == UserRole.BLOCKED:
            user.block_reason = block_reason
            user.restrict_mode = restrict_mode
            user.blocked_by = blocked_by
        else:
            user.block_reason = ""
            user.restrict_mode = RestrictMode.BOTH
            user.blocked_by = None
        return user

    async def touch(
        self,
        user_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> AppUser:
        """Create or refresh the profile fields of a seen user.

        Called by the access middleware on every update from a PM/source chat,
        so admins see up-to-date names and newly-seen users get a row
        (role=UNKNOWN) that an admin can later promote.

        Uses an atomic SQLite upsert: when the bot catches up on a backlog,
        updates are dispatched concurrently, so two resolutions for the same
        brand-new user could both see no row and both INSERT, tripping the
        Users.id UNIQUE constraint. ON CONFLICT collapses that to one row.
        """
        values: dict[str, object] = {"id": user_id, "last_activity": datetime.now(UTC)}
        updates: dict[str, object] = {"last_activity": datetime.now(UTC)}
        if username is not None:
            values["username"] = username
            updates["username"] = username
        if first_name is not None:
            values["first_name"] = first_name
            updates["first_name"] = first_name
        if last_name is not None:
            values["last_name"] = last_name
            updates["last_name"] = last_name

        stmt = sqlite_insert(AppUser).values(**values)
        # only refresh profile fields and last_activity on conflict; never role
        stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=updates)
        await self._session.execute(stmt)

        user = await self.get(user_id)
        if user is None:  # defensive, unreachable in practice
            user = AppUser(id=user_id, role=UserRole.UNKNOWN)
            self._session.add(user)
        return user

    async def list_by_role(self, role: UserRole) -> list[AppUser]:
        stmt = select(AppUser).where(AppUser.role == role).order_by(AppUser.joined)
        result = await self._session.scalars(stmt)
        return list(result)
