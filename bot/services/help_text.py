"""Structured help text and command catalog, the single source of truth.

Defines which commands exist and which are common (all users) vs admin (STAFF
only). `build_help()` renders role-aware text for `/help`, `/start`, and the
inline-menu help button.

Imported by:
- `bot/commands.py`: registers BotCommand scopes with Telegram.
- `bot/handlers/common.py`: renders /help, /start, menu help callback.

When adding or renaming a command, update both the catalog here and the
handler.
"""

from __future__ import annotations

from aiogram.types import BotCommand

from bot import texts

# command catalog. order = display order in the BotFather menu and in /help
# text; descriptions live in bot/texts.py (CMD_DESC_COMMON / CMD_DESC_ADMIN).

# commands available to every user (in PM)
COMMON_COMMANDS: list[BotCommand] = [
    BotCommand(command=cmd, description=desc) for cmd, desc in texts.CMD_DESC_COMMON.items()
]

# staff-only extras, appended in the per-admin BotCommandScopeChat so admins
# see the full list in their PM menu
ADMIN_EXTRA_COMMANDS: list[BotCommand] = [
    BotCommand(command=cmd, description=desc) for cmd, desc in texts.CMD_DESC_ADMIN.items()
]


def build_help(*, bot_name: str, is_staff: bool = False) -> str:
    """Render /help text. Admin section is shown only to STAFF.

    `bot_name`: username without @, used in the mention example.
    `is_staff`: include the admin commands section.
    """
    parts: list[str] = [
        texts.ONBOARDING_TEXT.format(bot_name=bot_name),
        texts.HELP_COMMON_SECTION,
    ]
    if is_staff:
        parts.append(texts.HELP_ADMIN_SECTION)

    return "".join(parts)
