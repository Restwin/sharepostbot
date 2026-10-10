"""User-facing access commands: /whyblocked, /contacts.

/whyblocked (PM only, everyone): shows the user's role, block reason (if any)
and where they're restricted from publishing.

/contacts (PM only, everyone): lists the admin directory (public_role +
comment) with inline URL buttons to DM each admin.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import LinkPreviewOptions, Message
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import texts
from bot.config import Settings
from bot.services.access import AccessService, PublishChannel
from bot.services.access_messages import (
    build_admin_contacts_text,
    whyblocked_text,
)
from bot.services.membership import MembershipService

router = Router(name="access")


@router.message(Command("whyblocked"), F.chat.type == ChatType.PRIVATE)
async def cmd_whyblocked(
    message: Message,
    settings: Settings,
    access: AccessService,
    membership: MembershipService,
) -> None:
    user = message.from_user
    if user is None:
        return
    decision = await access.resolve(
        user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        channel=PublishChannel.PM,
    )
    is_member = None if decision.is_staff else await membership.is_member(user.id)
    text = whyblocked_text(decision, is_member=is_member)
    contacts_hint = texts.WHYBLOCKED_CONTACTS_HINT
    await message.answer(
        text + contacts_hint, link_preview_options=LinkPreviewOptions(is_disabled=True)
    )


@router.message(Command("contacts"), F.chat.type == ChatType.PRIVATE)
async def cmd_contacts(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    text, keyboard = await build_admin_contacts_text(session_factory)
    await message.answer(
        text,
        reply_markup=keyboard,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
    )
