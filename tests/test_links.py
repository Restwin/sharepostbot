"""Tests for the CommunityLinks repository and link rendering."""

from __future__ import annotations

from bot.db.models import CommunityLinks
from bot.db.repo.links import LINK_FIELDS, LinksRepository, link_label
from bot.handlers.links import render_links_text


async def test_links_repo_is_a_singleton_row(session_factory):
    async with session_factory() as session:
        repo = LinksRepository(session)
        row = await repo.get()
        assert row.id == 1
        assert row.rules_url is None
        assert row.channel_url is None
        assert row.main_chat_url is None
        await session.commit()

    async with session_factory() as session:
        repo = LinksRepository(session)
        again = await repo.get()
        assert again is not None


async def test_links_repo_set_and_clear(session_factory):
    async with session_factory() as session:
        repo = LinksRepository(session)
        await repo.set("channel", "https://t.me/chan")
        await repo.set("chat", "https://t.me/chat")
        await session.commit()

    async with session_factory() as session:
        repo = LinksRepository(session)
        row = await repo.get()
        assert row.channel_url == "https://t.me/chan"
        assert row.main_chat_url == "https://t.me/chat"
        assert row.rules_url is None

        await repo.clear("channel")
        await session.commit()
        row2 = await repo.get()
        assert row2.channel_url is None
        assert row2.main_chat_url == "https://t.me/chat"


def test_link_fields_mapping():
    assert LINK_FIELDS == {"rules": "rules_url", "channel": "channel_url", "chat": "main_chat_url"}
    assert link_label("rules") == "Правила публикации постов"
    assert link_label("channel") == "Канал"
    assert link_label("chat") == "Основной чат"


def test_render_links_text_placeholders():
    text = render_links_text(CommunityLinks(id=1))
    assert "не заполнена" in text
    assert "/links" in text


def test_render_links_text_filled():
    text = render_links_text(CommunityLinks(id=1, channel_url="https://t.me/chan"))
    assert "https://t.me/chan" in text
