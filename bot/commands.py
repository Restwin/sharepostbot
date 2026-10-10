"""Register bot commands with Telegram, split by user role.

Three scopes:
- default (everyone): common user commands
- all private chats: same list, keeps the PM menu consistent
- per-admin (BotCommandScopeChat): common + admin extras

The command catalog lives in `bot/services/help_text.py`. Called on startup in
both polling and webhook modes.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot.config import Settings
from bot.db.models import UserRole
from bot.db.repo.users import UserRepository
from bot.logging_setup import get_logger
from bot.services.help_text import ADMIN_EXTRA_COMMANDS, COMMON_COMMANDS

_log = get_logger("bot.commands")


async def register_commands(
    bot: Bot,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Set command menus for all users + per-admin scopes.

    Safe to call on every startup: Telegram replaces the previous menu.
    """
    # 1. default scope: everyone
    try:
        await bot.set_my_commands(COMMON_COMMANDS, scope=BotCommandScopeDefault())
    except Exception as exc:
        _log.warning("set_my_commands_default_failed", error=str(exc))

    # 2. all private chats: same list, so the PM menu stays consistent even if
    #    a group-specific scope was set elsewhere
    try:
        await bot.set_my_commands(COMMON_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    except Exception as exc:
        _log.warning("set_my_commands_private_failed", error=str(exc))

    # 3. per-admin scopes: each STAFF user sees the extended list
    staff_ids = set(settings.admin_ids)
    # include DB-staff too, so admins promoted via /users get the menu after
    # a restart
    try:
        async with session_factory() as session:
            repo = UserRepository(session)
            db_staff = await repo.list_by_role(UserRole.STAFF)
            staff_ids.update(u.id for u in db_staff)
    except Exception as exc:
        _log.warning("list_staff_failed", error=str(exc))

    staff_commands: list[BotCommand] = COMMON_COMMANDS + ADMIN_EXTRA_COMMANDS
    for admin_id in staff_ids:
        try:
            await bot.set_my_commands(
                staff_commands,
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
            _log.debug("set_admin_commands", admin_id=admin_id)
        except Exception as exc:
            _log.warning("set_my_commands_admin_failed", admin_id=admin_id, error=str(exc))

    _log.info(
        "commands_registered",
        user_commands=len(COMMON_COMMANDS),
        staff_commands=len(staff_commands),
        staff_count=len(staff_ids),
    )
