"""Tests for the access-control service: role resolution, block reasons, channels."""

from __future__ import annotations

import pytest

from bot.config import Settings
from bot.db.models import RestrictMode, UserRole
from bot.db.repo.users import UserRepository
from bot.services.access import AccessService, PublishChannel


def _settings(admin_ids: list[int] | None = None) -> Settings:
    """settings with a dummy token"""
    return Settings(  # type: ignore[call-arg]
        bot_token="1234567890:AAA-test",
        bot_name="testbot",
        main_channel_id=-100,
        admin_ids=admin_ids or [],
    )


@pytest.mark.asyncio
async def test_unknown_user_allowed_by_default(session_factory):
    """UNKNOWN is a regular user, not a block; membership gates guests"""
    svc = AccessService(_settings(), session_factory)
    d_pm = await svc.resolve(999, channel=PublishChannel.PM)
    d_mention = await svc.resolve(999, channel=PublishChannel.MENTION)
    assert d_pm.role == UserRole.UNKNOWN
    assert d_pm.allowed
    assert d_mention.allowed
    assert not d_pm.is_staff


@pytest.mark.asyncio
async def test_super_admin_id_overrides_db(session_factory):
    svc = AccessService(_settings(admin_ids=[111]), session_factory)
    # block 111 in the DB first; super-admin overrides it
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.set_role(111, UserRole.BLOCKED, block_reason="test")
        await session.commit()

    d = await svc.resolve(111, channel=PublishChannel.PM)
    assert d.is_staff
    assert d.role == UserRole.STAFF
    assert d.allowed


@pytest.mark.asyncio
async def test_allow_role_can_publish_everywhere(session_factory):
    svc = AccessService(_settings(), session_factory)
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.set_role(222, UserRole.ALLOW)
        await session.commit()

    d_pm = await svc.resolve(222, channel=PublishChannel.PM)
    d_mention = await svc.resolve(222, channel=PublishChannel.MENTION)
    assert d_pm.allowed
    assert d_mention.allowed


@pytest.mark.asyncio
async def test_blocked_both_cannot_publish_anywhere(session_factory):
    svc = AccessService(_settings(), session_factory)
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.set_role(
            333,
            UserRole.BLOCKED,
            block_reason="spam",
            restrict_mode=RestrictMode.BOTH,
        )
        await session.commit()

    d_pm = await svc.resolve(333, channel=PublishChannel.PM)
    d_mention = await svc.resolve(333, channel=PublishChannel.MENTION)
    assert not d_pm.allowed
    assert not d_mention.allowed
    assert d_pm.block_reason == "spam"


@pytest.mark.asyncio
async def test_blocked_pm_only_can_mention(session_factory):
    svc = AccessService(_settings(), session_factory)
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.set_role(
            444,
            UserRole.BLOCKED,
            block_reason="no pm",
            restrict_mode=RestrictMode.PM_ONLY,
        )
        await session.commit()

    d_pm = await svc.resolve(444, channel=PublishChannel.PM)
    d_mention = await svc.resolve(444, channel=PublishChannel.MENTION)
    assert not d_pm.allowed  # blocked in PM
    assert d_mention.allowed  # but mention still works


@pytest.mark.asyncio
async def test_blocked_mention_only_can_pm(session_factory):
    svc = AccessService(_settings(), session_factory)
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.set_role(
            555,
            UserRole.BLOCKED,
            block_reason="no mention",
            restrict_mode=RestrictMode.MENTION_ONLY,
        )
        await session.commit()

    d_pm = await svc.resolve(555, channel=PublishChannel.PM)
    d_mention = await svc.resolve(555, channel=PublishChannel.MENTION)
    assert d_pm.allowed  # PM ok
    assert not d_mention.allowed  # mention blocked


@pytest.mark.asyncio
async def test_touch_creates_user_row(session_factory):
    svc = AccessService(_settings(), session_factory)
    await svc.resolve(777, username="bob", first_name="Bob")
    async with session_factory() as session:
        repo = UserRepository(session)
        user = await repo.get(777)
        assert user is not None
        assert user.username == "bob"
        assert user.first_name == "Bob"
        assert user.role == UserRole.UNKNOWN
