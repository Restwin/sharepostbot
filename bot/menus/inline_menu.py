"""Inline-keyboard menu. Role-aware, with submenus for admin commands.

The main menu shows every command the user is entitled to. Admin multi-variant
commands (users, admin_contacts, categories, stats, links) open submenus. The
bottom two rows are community info links (rules / channel / main chat) whose
URLs are set by admins via `/links`; empty links render as placeholders.
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.db.models import CommunityLinks
from bot.texts import (
    LIST_PAGE_MARKER,
    MENU_BTN_ADD_CHAT,
    MENU_BTN_ALL_CHATS,
    MENU_BTN_ALL_POSTS,
    MENU_BTN_BACK,
    MENU_BTN_BACKUP,
    MENU_BTN_BLOCK_CHAT,
    MENU_BTN_CATEGORIES,
    MENU_BTN_CATEGORIES_ADD,
    MENU_BTN_CATEGORIES_HIDE,
    MENU_BTN_CATEGORIES_ORDER,
    MENU_BTN_CATEGORIES_REMOVE,
    MENU_BTN_CATEGORIES_SHOW,
    MENU_BTN_CHANNEL,
    MENU_BTN_CHAT_MANAGE,
    MENU_BTN_CONTACTS,
    MENU_BTN_CONTACTS_ADD,
    MENU_BTN_CONTACTS_LIST,
    MENU_BTN_CONTACTS_ORDER,
    MENU_BTN_CONTACTS_REMOVE,
    MENU_BTN_CREATE_POST,
    MENU_BTN_HELP,
    MENU_BTN_LINKS,
    MENU_BTN_LINKS_CHANNEL,
    MENU_BTN_LINKS_CHAT,
    MENU_BTN_LINKS_RULES,
    MENU_BTN_LINKS_SHOW,
    MENU_BTN_MAIN_CHAT,
    MENU_BTN_MY_CHATS,
    MENU_BTN_MY_POSTS,
    MENU_BTN_PAGE_FIRST,
    MENU_BTN_PAGE_LAST,
    MENU_BTN_PAGE_NEXT,
    MENU_BTN_PAGE_PREV,
    MENU_BTN_REMOVE_CHAT,
    MENU_BTN_RULES,
    MENU_BTN_STATS,
    MENU_BTN_STATS_CATEGORIES,
    MENU_BTN_STATS_RECENT,
    MENU_BTN_STATS_USER,
    MENU_BTN_STATS_USERS,
    MENU_BTN_UNBLOCK_CHAT,
    MENU_BTN_USERS,
    MENU_BTN_USERS_BLOCK,
    MENU_BTN_USERS_LIST,
    MENU_BTN_USERS_SET,
    MENU_BTN_USERS_UNBLOCK,
    MENU_BTN_VERSION,
)
from bot.utils.callbacks import MenuCallback, WizardCallback


def _cb(action: str, sub: str = "") -> str:
    return MenuCallback(action=action, sub=sub).pack()


def _wizard_start() -> str:
    return WizardCallback(action="start").pack()


def _btn(text: str, action: str, sub: str = "") -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=_cb(action, sub))


def back_button() -> InlineKeyboardButton:
    """'⬅️ Назад' button: returns to the main menu (MenuCallback action='back')."""
    return _btn(MENU_BTN_BACK, "back")


def _info_btn(
    text: str,
    url: str | None,
    key: str,
    icon_custom_emoji_id: str = "",
) -> InlineKeyboardButton:
    icon: str | None = icon_custom_emoji_id or None
    if url:
        return InlineKeyboardButton(text=text, url=url, icon_custom_emoji_id=icon)
    return InlineKeyboardButton(
        text=text,
        callback_data=_cb("link_missing", key),
        icon_custom_emoji_id=icon,
    )


def main_menu(
    is_staff: bool,
    links: CommunityLinks | None,
    *,
    link_icon_custom_emoji_id: str = "",
) -> InlineKeyboardMarkup:
    rules = links.rules_url if links else None
    channel = links.channel_url if links else None
    chat = links.main_chat_url if links else None

    posts_btn = (
        _btn(MENU_BTN_ALL_POSTS, "all_posts") if is_staff else _btn(MENU_BTN_MY_POSTS, "myposts")
    )
    chats_btn = (
        _btn(MENU_BTN_ALL_CHATS, "all_chats") if is_staff else _btn(MENU_BTN_MY_CHATS, "my_chats")
    )
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=MENU_BTN_CREATE_POST, callback_data=_wizard_start()), posts_btn],
        [_btn(MENU_BTN_ADD_CHAT, "add_chat"), chats_btn],
    ]

    if is_staff:
        rows.append([_btn(MENU_BTN_USERS, "users"), _btn(MENU_BTN_STATS, "stats")])
        rows.append([_btn(MENU_BTN_CATEGORIES, "categories")])

    rows.append([_btn(MENU_BTN_HELP, "help"), _btn(MENU_BTN_CONTACTS, "contacts")])

    if is_staff:
        rows.append(
            [
                _btn(MENU_BTN_LINKS, "links"),
                _btn(MENU_BTN_VERSION, "version"),
                _btn(MENU_BTN_BACKUP, "backup_db"),
            ]
        )

    rows.append([_info_btn(MENU_BTN_RULES, rules, "rules", link_icon_custom_emoji_id)])
    rows.append(
        [
            _info_btn(MENU_BTN_CHANNEL, channel, "channel", link_icon_custom_emoji_id),
            _info_btn(MENU_BTN_MAIN_CHAT, chat, "chat", link_icon_custom_emoji_id),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _page_nav_row(action: str, page: int, pages: int) -> list[InlineKeyboardButton]:
    """Row of up to five nav buttons; the page marker in the middle is a no-op."""
    row: list[InlineKeyboardButton] = []
    if page > 1:
        row.append(_btn(MENU_BTN_PAGE_FIRST, action, "1"))
        row.append(_btn(MENU_BTN_PAGE_PREV, action, str(page - 1)))
    row.append(_btn(LIST_PAGE_MARKER.format(page=page, pages=pages), "page_marker"))
    if page < pages:
        row.append(_btn(MENU_BTN_PAGE_NEXT, action, str(page + 1)))
        row.append(_btn(MENU_BTN_PAGE_LAST, action, str(pages)))
    return row


def chats_page_menu(page: int, pages: int, *, admin: bool = False) -> InlineKeyboardMarkup:
    """Chats list screen: pagination nav + back (and «Управление» for admins)."""
    rows: list[list[InlineKeyboardButton]] = []
    if pages > 1:
        rows.append(_page_nav_row("all_chats" if admin else "my_chats", page, pages))
    bottom = [_btn(MENU_BTN_BACK, "back")]
    if admin:
        bottom.append(_btn(MENU_BTN_CHAT_MANAGE, "chat_manage"))
    rows.append(bottom)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def users_page_menu(page: int, pages: int) -> InlineKeyboardMarkup:
    """Users list screen: pagination nav + back."""
    rows: list[list[InlineKeyboardButton]] = []
    if pages > 1:
        rows.append(_page_nav_row("users", page, pages))
    rows.append([_btn(MENU_BTN_BACK, "back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def chat_manage_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(MENU_BTN_REMOVE_CHAT, "remove_chat")],
            [_btn(MENU_BTN_BLOCK_CHAT, "block_chat")],
            [_btn(MENU_BTN_UNBLOCK_CHAT, "unblock_chat")],
            [_btn(MENU_BTN_BACK, "back")],
        ]
    )


def users_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(MENU_BTN_USERS_LIST, "users", "list")],
            [_btn(MENU_BTN_USERS_SET, "users", "set")],
            [_btn(MENU_BTN_USERS_BLOCK, "users", "block")],
            [_btn(MENU_BTN_USERS_UNBLOCK, "users", "unblock")],
            [_btn(MENU_BTN_BACK, "back")],
        ]
    )


def admin_contacts_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(MENU_BTN_CONTACTS_LIST, "admin_contacts", "list")],
            [_btn(MENU_BTN_CONTACTS_ADD, "admin_contacts", "add")],
            [_btn(MENU_BTN_CONTACTS_REMOVE, "admin_contacts", "remove")],
            [_btn(MENU_BTN_CONTACTS_ORDER, "admin_contacts", "order")],
            [_btn(MENU_BTN_BACK, "back")],
        ]
    )


def categories_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                _btn(MENU_BTN_CATEGORIES_ADD, "categories", "add"),
                _btn(MENU_BTN_CATEGORIES_REMOVE, "categories", "remove"),
            ],
            [
                _btn(MENU_BTN_CATEGORIES_HIDE, "categories", "hide"),
                _btn(MENU_BTN_CATEGORIES_SHOW, "categories", "show"),
            ],
            [_btn(MENU_BTN_CATEGORIES_ORDER, "categories", "order")],
            [_btn(MENU_BTN_BACK, "back")],
        ]
    )


def stats_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(MENU_BTN_STATS_RECENT, "stats", "recent")],
            [_btn(MENU_BTN_STATS_CATEGORIES, "stats", "categories")],
            [_btn(MENU_BTN_STATS_USERS, "stats", "users")],
            [_btn(MENU_BTN_STATS_USER, "stats", "user")],
            [_btn(MENU_BTN_BACK, "back")],
        ]
    )


def links_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_btn(MENU_BTN_LINKS_RULES, "links_set", "rules")],
            [_btn(MENU_BTN_LINKS_CHANNEL, "links_set", "channel")],
            [_btn(MENU_BTN_LINKS_CHAT, "links_set", "chat")],
            [_btn(MENU_BTN_LINKS_SHOW, "links_show")],
            [_btn(MENU_BTN_BACK, "back")],
        ]
    )
