"""CallbackData classes for inline keyboards."""

from __future__ import annotations

from typing import Literal

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup

from bot.texts import CATEGORY_BTN_CANCEL


class MenuCallback(CallbackData, prefix="menu"):
    action: str
    sub: str = ""


class WizardCallback(CallbackData, prefix="wz"):
    action: str  # "publish", "cancel", "start"


class OnboardingCallback(CallbackData, prefix="onboard"):
    action: Literal["admin", "admin_confirm", "admin_open", "member", "leave"]
    chat_id: int
    inviter_id: int


class CategoryCallback(CallbackData, prefix="cat"):
    action: str  # "select" | "cancel"
    scope: str  # "wizard" | "repost"
    category_id: int = 0


class PostManageCallback(CallbackData, prefix="postm"):
    action: str  # "delete" | "edit"
    post_id: int


class RolePickCallback(CallbackData, prefix="rolepick"):
    """Role choice for the menu-driven user management FSM."""

    role: str  # "unknown" | "allow" | "blocked" | "staff"


class RepostPollCallback(CallbackData, prefix="rpoll"):
    action: str  # "forward" | "cancel"


def category_keyboard(categories: list[tuple[int, str]], scope: str) -> InlineKeyboardMarkup:
    """Inline keyboard of categories: one button per category + a cancel button."""
    from aiogram.utils.keyboard import InlineKeyboardBuilder

    builder = InlineKeyboardBuilder()
    for category_id, name in categories:
        builder.button(
            text=name,
            callback_data=CategoryCallback(action="select", scope=scope, category_id=category_id),
        )
    builder.button(
        text=CATEGORY_BTN_CANCEL,
        callback_data=CategoryCallback(action="cancel", scope=scope),
    )
    builder.adjust(1)
    return builder.as_markup()
