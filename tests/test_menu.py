"""Tests for the role-aware inline menu and menu keyboard decision."""

from __future__ import annotations

from bot.config import Settings
from bot.db.models import AppUser, CommunityLinks, RestrictMode, UserRole
from bot.handlers.common import _menu_keyboard
from bot.menus.inline_menu import main_menu
from bot.services.access import AccessDecision


def _settings(**kwargs) -> Settings:
    return Settings(  # type: ignore[call-arg]
        bot_token="1234567890:AAA-test",
        bot_name="testbot",
        main_channel_id=-100,
        **kwargs,
    )


def _decision(role: UserRole, *, is_member: bool = True) -> AccessDecision:
    return AccessDecision(
        allowed=role != UserRole.BLOCKED,
        role=role,
        is_staff=role == UserRole.STAFF,
        block_reason="",
        restrict_mode=RestrictMode.BOTH,
        user=AppUser(id=1, role=role),
    )


def _buttons(markup):
    return [b for row in markup.inline_keyboard for b in row]


def _texts(markup):
    return [b.text for b in _buttons(markup)]


def test_user_menu_excludes_admin_sections():
    texts = _texts(main_menu(False, None))
    assert "📝 Создать пост" in texts
    assert "🔍 Мои посты" in texts
    assert "➕ Добавить чат" in texts
    assert "📋 Мои чаты" in texts
    assert "ℹ️ Помощь" in texts
    assert "📇 Админы бота" in texts
    assert "👥 Пользователи" not in texts
    assert "📊 Статистика" not in texts
    assert "🔗 Ссылки" not in texts
    assert "📋 Все посты" not in texts


def test_admin_menu_includes_admin_sections():
    texts = _texts(main_menu(True, None))
    assert "📋 Все посты" in texts
    assert "📋 Все чаты" in texts
    assert "👥 Пользователи" in texts
    assert "📇 Админы бота" in texts
    assert "🏷 Категории" in texts
    assert "📊 Статистика" in texts
    assert "🔗 Ссылки" in texts
    assert "🗑 Управление чатами" not in texts
    assert "🗑🚫 Управление" not in texts  # moved into the all-chats screen


def test_menu_always_ends_with_info_rows():
    rows = main_menu(False, None).inline_keyboard
    # penultimate row = rules; last row = channel + chat (links in corner).
    assert [b.text for b in rows[-2]] == ["📜 Правила публикации постов"]
    assert [b.text for b in rows[-1]] == ["📢 Канал", "💬 Основной чат"]


def test_user_menu_groupings():
    texts = [[b.text for b in r] for r in main_menu(False, None).inline_keyboard]
    assert ["📝 Создать пост", "🔍 Мои посты"] in texts
    assert ["➕ Добавить чат", "📋 Мои чаты"] in texts
    assert ["ℹ️ Помощь", "📇 Админы бота"] in texts


def test_admin_menu_groupings():
    texts = [[b.text for b in r] for r in main_menu(True, None).inline_keyboard]
    assert ["📝 Создать пост", "📋 Все посты"] in texts
    assert ["➕ Добавить чат", "📋 Все чаты"] in texts
    assert ["👥 Пользователи", "📊 Статистика"] in texts
    assert ["🏷 Категории"] in texts
    assert ["ℹ️ Помощь", "📇 Админы бота"] in texts
    assert ["🔗 Ссылки", "ℹ️ Версия", "🗄 Бэкап БД"] in texts


def test_link_buttons_use_corner_icon_when_configured():
    rows = main_menu(False, None).inline_keyboard
    # no icon configured: link buttons carry no custom emoji id
    assert rows[-2][0].text == "📜 Правила публикации постов"
    assert rows[-2][0].icon_custom_emoji_id is None
    assert rows[-1][0].icon_custom_emoji_id is None

    rows2 = main_menu(False, None, link_icon_custom_emoji_id="5368324170671202286").inline_keyboard
    assert rows2[-2][0].icon_custom_emoji_id == "5368324170671202286"
    assert rows2[-1][0].icon_custom_emoji_id == "5368324170671202286"
    assert rows2[-1][1].icon_custom_emoji_id == "5368324170671202286"


def test_info_buttons_placeholder_vs_url():
    rows = main_menu(False, None).inline_keyboard
    channel_btn = rows[-1][0]
    assert channel_btn.url is None
    assert "link_missing" in (channel_btn.callback_data or "")

    links = CommunityLinks(id=1, channel_url="https://t.me/chan", main_chat_url="https://t.me/chat")
    rows2 = main_menu(False, links).inline_keyboard
    assert rows2[-1][0].url == "https://t.me/chan"
    assert rows2[-1][1].url == "https://t.me/chat"


async def test_menu_keyboard_none_for_blocked(session_factory):
    assert (
        await _menu_keyboard(_decision(UserRole.BLOCKED), True, session_factory, _settings())
        is None
    )


async def test_menu_keyboard_none_for_guest(session_factory):
    decision = _decision(UserRole.UNKNOWN)
    assert await _menu_keyboard(decision, False, session_factory, _settings()) is None


async def test_menu_keyboard_present_for_member(session_factory):
    decision = _decision(UserRole.UNKNOWN)
    kb = await _menu_keyboard(decision, True, session_factory, _settings())
    assert kb is not None
    assert "👥 Пользователи" not in _texts(kb)


async def test_menu_keyboard_present_for_staff(session_factory):
    kb = await _menu_keyboard(_decision(UserRole.STAFF), False, session_factory, _settings())
    assert kb is not None
    assert "👥 Пользователи" in _texts(kb)
