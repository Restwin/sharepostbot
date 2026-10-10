"""Access control service: resolve a user's role and publication rights.

Access model (four categories):
- STAFF: administrator; full access, bypasses the channel-membership gate.
- BLOCKED: explicitly banned; denied per `restrict_mode`, regardless of
  membership. Can still use /whyblocked and /contacts in PM.
- Regular: role UNKNOWN (default) or ALLOW (explicit positive marker). May
  publish, but channel membership is enforced separately at the call sites
  (middleware). UNKNOWN is not a block: being in the community channel is
  enough to publish.
- Guest: a regular user who is not a member of the main channel. Cannot
  publish; the membership gate shows the guest message.

Role resolution priority:
1. `Settings.admin_ids` (env): bootstrap super-admins, always STAFF regardless
   of DB state, so the first admin can be set without DB access.
2. `AppUser.role` in DB: STAFF / ALLOW / BLOCKED / UNKNOWN.
3. Default: UNKNOWN (regular user; membership gate decides access).

The service also touches the user row on first sight so admins can see
newly-seen users in the admin directory and promote them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.db.models import AppUser, RestrictMode, UserRole
from bot.db.repo.users import UserRepository


class PublishChannel(IntEnum):
    """Where a user is trying to publish from."""

    PM = 0  # /post wizard in private chat
    MENTION = 1  # reply + @bot mention in a source chat


@dataclass(frozen=True, slots=True)
class AccessDecision:
    """Result of an access check.

    `user` is the AppUser row created/updated by the check (committed).
    `block_reason` is free-form text shown to the user via /whyblocked.
    """

    allowed: bool
    role: UserRole
    is_staff: bool
    block_reason: str
    restrict_mode: RestrictMode
    user: AppUser
    blocked_by_name: str | None = None


class AccessService:
    """Resolve access for a user on a given publication channel."""

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory

    async def resolve(
        self,
        user_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        last_name: str | None = None,
        channel: PublishChannel | None = None,
    ) -> AccessDecision:
        """Resolve access for the user and commit the touched/updated user row."""
        async with self._session_factory() as session:
            repo = UserRepository(session)
            user = await repo.touch(
                user_id,
                username=username,
                first_name=first_name,
                last_name=last_name,
            )

            # env super-admin overrides the DB role
            blocked_by_name: str | None = None
            if self._settings.is_super_admin(user_id):
                if user.role != UserRole.STAFF:
                    user.role = UserRole.STAFF
                is_staff = True
                role = UserRole.STAFF
                block_reason = ""
                restrict_mode = RestrictMode.BOTH
            else:
                role = user.role
                is_staff = role == UserRole.STAFF
                block_reason = user.block_reason
                restrict_mode = user.restrict_mode
                if role == UserRole.BLOCKED and user.blocked_by is not None:
                    admin = await repo.get(user.blocked_by)
                    if admin is not None:
                        blocked_by_name = (
                            f"@{admin.username}"
                            if admin.username
                            else (admin.first_name or admin.last_name or f"id:{admin.id}")
                        )
                    else:
                        blocked_by_name = f"id:{user.blocked_by}"

            await session.commit()

        allowed = _decide_allowed(role, restrict_mode, channel)
        return AccessDecision(
            allowed=allowed,
            role=role,
            is_staff=is_staff,
            block_reason=block_reason,
            restrict_mode=restrict_mode,
            user=user,
            blocked_by_name=blocked_by_name,
        )


def _decide_allowed(
    role: UserRole,
    restrict_mode: RestrictMode,
    channel: PublishChannel | None,
) -> bool:
    """Pure function: can a user with this role publish on this channel?

    STAFF, ALLOW and UNKNOWN are permitted here; membership is enforced
    separately at the call sites, so UNKNOWN means "not banned", not "pending
    vetting". BLOCKED is denied per `restrict_mode`.
    """
    if role in (UserRole.STAFF, UserRole.ALLOW, UserRole.UNKNOWN):
        return True
    # blocked: depends on restrict_mode and channel
    if channel is None:
        # no channel given, report the role-level block only
        return False
    if channel == PublishChannel.PM:
        return restrict_mode == RestrictMode.MENTION_ONLY
    if channel == PublishChannel.MENTION:
        return restrict_mode == RestrictMode.PM_ONLY
    return False
