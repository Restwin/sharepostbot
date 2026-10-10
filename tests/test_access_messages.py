"""Tests for access_messages: /whyblocked text, blocked replies, role labels."""

from __future__ import annotations

from bot.db.models import AppUser, RestrictMode, UserRole
from bot.db.repo.users import UserRepository
from bot.services.access import AccessDecision
from bot.services.access_messages import (
    blocked_chat_lines,
    blocked_mention_reply,
    blocked_pm_reply,
    build_guest_message,
    not_member_mention_reply,
    resolve_user_handle,
    role_label_ru,
    whyblocked_text,
)


def _decision(
    role: UserRole,
    *,
    block_reason: str = "",
    restrict_mode: RestrictMode = RestrictMode.BOTH,
    blocked_by_name: str | None = None,
) -> AccessDecision:
    user = AppUser(id=42, role=role, first_name="Test")
    return AccessDecision(
        allowed=False,
        role=role,
        is_staff=role == UserRole.STAFF,
        block_reason=block_reason,
        restrict_mode=restrict_mode,
        user=user,
        blocked_by_name=blocked_by_name,
    )


def test_role_label_ru():
    assert role_label_ru(UserRole.STAFF) == "админ"
    assert role_label_ru(UserRole.ALLOW) == "пользователь с доступом"
    assert role_label_ru(UserRole.BLOCKED) == "доступ ограничен"
    assert role_label_ru(UserRole.UNKNOWN) == "пользователь"


def test_blocked_mention_reply_includes_reason_and_whyblocked_hint():
    d = _decision(UserRole.BLOCKED, block_reason="spam")
    text = blocked_mention_reply(d)
    assert "spam" in text
    assert "/whyblocked" in text
    assert "упоминание" in text


def test_blocked_mention_reply_handles_missing_reason():
    d = _decision(UserRole.BLOCKED, block_reason="")
    text = blocked_mention_reply(d)
    assert "причина не указана" in text


def test_blocked_pm_reply_for_blocked_includes_reason():
    d = _decision(UserRole.BLOCKED, block_reason="banned for spam")
    text = blocked_pm_reply(d)
    assert "banned for spam" in text
    assert "/whyblocked" in text


def test_not_member_mention_reply_points_to_recheck():
    text = not_member_mention_reply()
    assert "/recheck" in text
    assert "канал" in text


def test_whyblocked_text_for_blocked_includes_reason_and_mode():
    d = _decision(
        UserRole.BLOCKED,
        block_reason="violated rules",
        restrict_mode=RestrictMode.PM_ONLY,
    )
    text = whyblocked_text(d)
    assert "доступ ограничен" in text
    assert "violated rules" in text
    assert "только ЛС" in text  # mode label


def test_whyblocked_text_for_allow_says_no_restrictions():
    d = _decision(UserRole.ALLOW)
    text = whyblocked_text(d)
    assert "Ограничений нет" in text


def test_whyblocked_text_for_blocked_includes_blocker():
    d = _decision(UserRole.BLOCKED, block_reason="spam", blocked_by_name="@admin")
    text = whyblocked_text(d)
    assert "Заблокировал:" in text
    assert "@admin" in text


def test_whyblocked_text_omits_blocker_when_unknown():
    d = _decision(UserRole.BLOCKED, block_reason="spam")
    text = whyblocked_text(d)
    assert "Заблокировал:" not in text


def test_whyblocked_text_for_unknown_says_no_restrictions():
    d = _decision(UserRole.UNKNOWN)
    text = whyblocked_text(d)
    assert "пользователь" in text
    assert "Ограничений нет" in text


def test_whyblocked_text_adds_membership_note_for_non_member():
    d = _decision(UserRole.UNKNOWN)
    text = whyblocked_text(d, is_member=False)
    assert "не состоите в канале" in text

    # staff never get the membership note, even with is_member=False
    staff = _decision(UserRole.STAFF)
    assert "не состоите в канале" not in whyblocked_text(staff, is_member=False)


async def test_guest_message_includes_contacts_and_recheck(session_factory):
    text = await build_guest_message(session_factory)
    assert "/recheck" in text
    assert "Админы сообщества" in text or "Список админов" in text


async def test_resolve_user_handle_prefers_username(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.touch(42, username="admin", first_name="Admin")
        await session.commit()
    assert await resolve_user_handle(session_factory, 42) == "@admin"


async def test_resolve_user_handle_falls_back_to_name(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.touch(43, first_name="John", last_name="Doe")
        await session.commit()
    assert await resolve_user_handle(session_factory, 43) == "John Doe"


async def test_resolve_user_handle_unknown_id(session_factory):
    assert await resolve_user_handle(session_factory, 999999) == "id:999999"


async def test_blocked_chat_lines_includes_reason_and_blocker(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.touch(42, username="admin", first_name="Admin")
        await session.commit()
    lines = await blocked_chat_lines(session_factory, block_reason="спам", blocked_by=42)
    assert any("спам" in line for line in lines)
    assert any("@admin" in line for line in lines)


async def test_blocked_chat_lines_missing_reason_and_blocker(session_factory):
    lines = await blocked_chat_lines(session_factory, block_reason="", blocked_by=None)
    assert any("причина не указана" in line for line in lines)
    assert not any("Заблокировал" in line for line in lines)
