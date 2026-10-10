"""Tests for the role-aware help text and command catalog."""

from __future__ import annotations

from bot.services.help_text import ADMIN_EXTRA_COMMANDS, COMMON_COMMANDS, build_help


def test_no_duplicate_access_section():
    text = build_help(bot_name="b", is_staff=False)
    assert "Доступ:" not in text


def test_admin_section_only_for_staff():
    assert "Команды админа" in build_help(bot_name="b", is_staff=True)
    assert "Команды админа" not in build_help(bot_name="b", is_staff=False)


def test_command_catalogs_do_not_overlap():
    common = {c.command for c in COMMON_COMMANDS}
    extra = {c.command for c in ADMIN_EXTRA_COMMANDS}
    assert not common & extra


def test_help_resolves_bot_name_from_onboarding_text():
    text = build_help(bot_name="mybot", is_staff=False)
    assert "<b>mybot</b>" in text
    assert "{bot_name}" not in text
    assert "Команды (в ЛС):" in text


def test_onboarding_text_common_plus_tails():
    from bot.handlers.onboarding import _onboarding_text

    fresh = _onboarding_text("mybot")
    assert fresh.startswith("👋 Привет!")
    assert "<b>mybot</b>" in fresh
    assert "Этого чата ещё нет в моём списке" in fresh

    registered = _onboarding_text("mybot", registered=True)
    assert "Этого чата ещё нет" not in registered
    assert "уже есть в моём списке" in registered


def test_add_chat_and_recheck_are_common():
    common = {c.command for c in COMMON_COMMANDS}
    assert "add_chat" in common
    assert "recheck" in common


def test_add_this_chat_removed():
    common = {c.command for c in COMMON_COMMANDS}
    extra = {c.command for c in ADMIN_EXTRA_COMMANDS}
    assert "add_this_chat" not in common
    assert "add_this_chat" not in extra
