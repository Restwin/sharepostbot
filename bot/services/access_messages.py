"""Helpers to render the /whyblocked and access-denied messages.

Shared by the access middleware and the /whyblocked command so both use the
same wording.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import texts
from bot.config import Settings
from bot.db.models import UserRole
from bot.db.repo.contacts import AdminContactRepository
from bot.db.repo.users import UserRepository
from bot.services.access import AccessDecision, AccessService, PublishChannel
from bot.utils.formatting import html_escape
from bot.utils.replies import temp_reply

_ROLE_LABEL_RU = {
    UserRole.STAFF: texts.ROLE_LABEL_STAFF,
    UserRole.ALLOW: texts.ROLE_LABEL_ALLOW,
    UserRole.BLOCKED: texts.ROLE_LABEL_BLOCKED,
    UserRole.UNKNOWN: texts.ROLE_LABEL_UNKNOWN,
}


def role_label_ru(role: UserRole) -> str:
    return _ROLE_LABEL_RU.get(role, texts.ROLE_LABEL_OTHER)


async def require_staff(
    message: Message,
    access: AccessService,
    *,
    deny_text: str = texts.ADMIN_ONLY,
) -> bool:
    """Return True if the sender is STAFF (env super-admin or DB role).

    Otherwise replies `deny_text` (best-effort) and returns False. Central
    access gate for every admin-only command handler.
    """
    user = message.from_user
    if user is None:
        return False
    decision = await access.resolve(
        user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        channel=PublishChannel.PM,
    )
    if not decision.is_staff:
        await temp_reply(message, deny_text)
        return False
    return True


async def collect_staff_ids(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> set[int]:
    """Union of env bootstrap ADMIN_IDS and DB STAFF users."""
    ids = set(settings.admin_ids)
    async with session_factory() as session:
        for user in await UserRepository(session).list_by_role(UserRole.STAFF):
            ids.add(user.id)
    return ids


async def build_admin_contacts_text(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Return (text, inline_keyboard) for the admin directory.

    Each admin is listed as `@username - role (comment)`. The keyboard gets a
    URL button per admin with a known username so users can DM them; None
    keyboard when no admin has a username.
    """
    async with session_factory() as session:
        repo = AdminContactRepository(session)
        user_repo = UserRepository(session)
        contacts = await repo.get_all()

        if not contacts:
            return (texts.CONTACTS_EMPTY, None)

        lines: list[str] = []
        buttons: list[InlineKeyboardButton] = []
        for c in contacts:
            user = await user_repo.get(c.user_id)
            display = (
                (user.first_name or user.username or f"id:{c.user_id}")
                if user
                else f"id:{c.user_id}"
            )
            username = user.username if user else None
            comment = f" — {html_escape(c.comment)}" if c.comment else ""
            role = html_escape(c.public_role)
            if username:
                handle = html_escape(f"@{username}")
                lines.append(f"• {handle} — {role}{comment}")
                buttons.append(
                    InlineKeyboardButton(
                        text=f"{display} ({c.public_role})",
                        url=f"https://t.me/{username}",
                    )
                )
            else:
                lines.append(f"• {html_escape(display)} — {role}{comment}")

        text = texts.CONTACTS_HEADER + "\n".join(lines)
        keyboard: InlineKeyboardMarkup | None = None
        if buttons:
            # one button per row, cleaner on mobile
            keyboard = InlineKeyboardMarkup(inline_keyboard=[[b] for b in buttons])
        return text, keyboard


async def build_guest_message(
    session_factory: async_sessionmaker[AsyncSession],
) -> str:
    """Full message for a non-member guest: not in channel + admin contacts + /recheck."""
    contacts_text, _ = await build_admin_contacts_text(session_factory)
    return texts.GUEST_MESSAGE.format(contacts=contacts_text)


def blocked_mention_reply(decision: AccessDecision) -> str:
    """Reply shown in a source chat when a BLOCKED user tries mention-posting."""
    reason = (
        html_escape(decision.block_reason) if decision.block_reason else texts.REASON_UNSPECIFIED
    )
    return texts.BLOCKED_MENTION_REPLY.format(reason=reason)


def not_member_mention_reply() -> str:
    """Short reply in a source chat when a non-member tries mention-posting."""
    return texts.NOT_MEMBER_MENTION_REPLY


def blocked_pm_reply(decision: AccessDecision) -> str:
    """Reply shown in PM when a BLOCKED user tries /post."""
    reason = (
        html_escape(decision.block_reason) if decision.block_reason else texts.REASON_UNSPECIFIED
    )
    return texts.BLOCKED_PM_REPLY.format(reason=reason)


def whyblocked_text(decision: AccessDecision, *, is_member: bool | None = None) -> str:
    """Full explanation for /whyblocked.

    When `is_member` is False, adds a membership note for non-STAFF users.
    """
    role = role_label_ru(decision.role)
    lines = [texts.WHYBLOCKED_STATUS.format(role=html_escape(role))]

    if decision.role == UserRole.BLOCKED:
        reason = decision.block_reason or texts.REASON_UNSPECIFIED
        lines.append(texts.WHYBLOCKED_REASON.format(reason=html_escape(reason)))
        mode = texts.RESTRICT_MODE_LABEL.get(
            str(int(decision.restrict_mode)), texts.RESTRICT_MODE_UNKNOWN
        )
        lines.append(texts.WHYBLOCKED_WHERE.format(mode=html_escape(mode)))
        if decision.blocked_by_name:
            lines.append(texts.WHYBLOCKED_BY.format(name=html_escape(decision.blocked_by_name)))
    else:
        lines.append(texts.WHYBLOCKED_NO_RESTRICTIONS)

    if is_member is False and not decision.is_staff:
        lines.append(texts.WHYBLOCKED_NOT_MEMBER)

    lines.append(texts.WHYBLOCKED_CONTACT_HINT)
    return "\n".join(lines)


async def resolve_user_handle(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
) -> str:
    """Resolve a user id to a display handle (@username / name / id:...)."""
    async with session_factory() as session:
        user = await UserRepository(session).get(user_id)
    if user is None:
        return f"id:{user_id}"
    if user.username:
        return f"@{user.username}"
    return " ".join(filter(None, [user.first_name, user.last_name])) or f"id:{user_id}"


async def blocked_chat_lines(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    block_reason: str,
    blocked_by: int | None,
) -> list[str]:
    """Reason + blocker lines for a blocked chat (symmetric with /whyblocked)."""
    reason = block_reason or texts.REASON_UNSPECIFIED
    lines = [texts.BLOCKED_CHAT_REASON_LINE.format(reason=html_escape(reason))]
    if blocked_by is not None:
        handle = await resolve_user_handle(session_factory, blocked_by)
        lines.append(texts.BLOCKED_CHAT_BY_LINE.format(name=html_escape(handle)))
    return lines
