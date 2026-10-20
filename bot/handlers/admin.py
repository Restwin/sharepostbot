"""Admin commands: /show_admins, /backup_db (sends the SQLite file to debug chats)."""

from __future__ import annotations

from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import texts
from bot.config import Settings
from bot.db.repo.users import UserRepository
from bot.logging_setup import get_logger
from bot.services.access import AccessService, PublishChannel
from bot.services.access_messages import collect_staff_ids
from bot.utils.formatting import html_escape
from bot.utils.replies import temp_reply

_log = get_logger("bot.admin")

router = Router(name="admin")


@router.message(Command("show_admins"), F.chat.type == ChatType.PRIVATE)
async def show_admins(
    message: Message,
    settings: Settings,
    access: AccessService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if not message.from_user:
        return
    decision = await access.resolve(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        channel=PublishChannel.PM,
    )
    if not decision.is_staff:
        await temp_reply(message, texts.ADMIN_ONLY_SHORT)
        return

    staff_ids = await collect_staff_ids(settings, session_factory)
    async with session_factory() as session:
        all_users = {usr.id: usr for usr in await UserRepository(session).get_all()}

    lines = []
    for uid in sorted(staff_ids):
        usr = all_users.get(uid)
        handle = f"@{usr.username}" if usr and usr.username else f"id:{uid}"
        lines.append(f"• {html_escape(handle)}")
    await message.reply(texts.ADMINS_HEADER + ("\n".join(lines) if lines else texts.ADMINS_EMPTY))


@router.message(Command("backup_db"), F.chat.type == ChatType.PRIVATE)
async def backup_db(
    message: Message,
    settings: Settings,
    bot: Bot,
    access: AccessService,
) -> None:
    if not message.from_user:
        return
    decision = await access.resolve(
        message.from_user.id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        channel=PublishChannel.PM,
    )
    if not decision.is_staff:
        await temp_reply(message, texts.ADMIN_ONLY_SHORT)
        return

    if not settings.backup_to_chat_enabled:
        await temp_reply(message, texts.BACKUP_DISABLED)
        return

    path = Path(settings.db_path)
    if not path.exists():
        await temp_reply(message, texts.BACKUP_NOT_FOUND.format(path=html_escape(str(path))))
        return

    # Snapshot via VACUUM INTO: copying the live DB file directly would miss
    # recent writes that are still in the WAL.
    from bot.services.backup import create_backup

    snapshot = await create_backup(settings)
    document = FSInputFile(snapshot, filename=snapshot.name)
    target_chats = settings.debug_info_chat_ids or [message.chat.id]
    for chat_id in target_chats:
        await bot.send_document(chat_id, document, caption="#backup")
    _log.info("backup_sent", target_chats=target_chats, to_tech="admin")
    await temp_reply(message, texts.BACKUP_SENT)
