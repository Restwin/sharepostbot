"""Tests for menu pagination, chat name/id resolution and order parsing."""

from __future__ import annotations

from bot.db.repo.chats import ChatRepository
from bot.db.repo.users import UserRepository
from bot.handlers.admin_users import _parse_order_pairs
from bot.handlers.chat_manage import _is_chat_id, _resolve_chat_ref
from bot.handlers.common import _parse_page, _total_pages
from bot.menus.inline_menu import chats_page_menu, users_page_menu

# pagination helpers


def test_parse_page_defaults_and_clamps():
    assert _parse_page("") == 1
    assert _parse_page("list") == 1
    assert _parse_page("0") == 1
    assert _parse_page("-3") == 1
    assert _parse_page("4") == 4


def test_total_pages():
    assert _total_pages(0, 20) == 1
    assert _total_pages(20, 20) == 1
    assert _total_pages(21, 20) == 2
    assert _total_pages(1, 1) == 1


def test_single_page_menus_have_no_nav_row():
    assert len(users_page_menu(1, 1).inline_keyboard) == 1  # back only
    assert len(chats_page_menu(1, 1, admin=True).inline_keyboard) == 1  # back + manage


def test_multi_page_nav_row_order():
    rows = users_page_menu(2, 5).inline_keyboard
    nav = [b.text for b in rows[0]]
    assert nav == ["⏮", "◀", "2/5", "▶", "⏭"]
    assert [b.text for b in rows[1]] == ["⬅️ Назад"]


def test_first_page_nav_hides_backward_buttons():
    nav = [b.text for b in users_page_menu(1, 3).inline_keyboard[0]]
    assert nav == ["1/3", "▶", "⏭"]


def test_chats_page_menu_admin_has_manage_button():
    rows = chats_page_menu(1, 1, admin=True).inline_keyboard
    assert [b.text for b in rows[-1]] == ["⬅️ Назад", "🗑🚫 Управление"]
    rows_member = chats_page_menu(1, 1, admin=False).inline_keyboard
    assert [b.text for b in rows_member[-1]] == ["⬅️ Назад"]


# chat name/id resolution


def test_is_chat_id():
    assert _is_chat_id("-1001234567890")
    assert _is_chat_id("123")
    assert not _is_chat_id("Some Chat")
    assert not _is_chat_id("")
    assert not _is_chat_id("-100abc")


async def test_resolve_chat_ref_by_id(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(chat_id=-100500, exact_name="A", join_link="")
        await session.commit()
        chat, matches = await _resolve_chat_ref(repo, "-100500")
        assert chat is not None and chat.chat_id == -100500
        assert matches == 1


async def test_resolve_chat_ref_unique_name(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(chat_id=-100501, exact_name="Solo", join_link="")
        await session.commit()
        chat, matches = await _resolve_chat_ref(repo, "Solo")
        assert chat is not None and chat.chat_id == -100501
        assert matches == 1


async def test_resolve_chat_ref_ambiguous_name(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(chat_id=-100502, exact_name="Twin", join_link="")
        await repo.add_or_update(chat_id=-100503, exact_name="Twin", join_link="")
        await session.commit()
        chat, matches = await _resolve_chat_ref(repo, "Twin")
        assert chat is None
        assert matches == 2
        # by id it resolves unambiguously
        chat2, matches2 = await _resolve_chat_ref(repo, "-100503")
        assert chat2 is not None and chat2.chat_id == -100503
        assert matches2 == 1


async def test_resolve_chat_ref_missing(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        chat, matches = await _resolve_chat_ref(repo, "NoSuchChat")
        assert chat is None
        assert matches == 0


# categories order parser


def test_parse_order_pairs_valid():
    assert _parse_order_pairs("3:1, 1:2") == [(3, 1), (1, 2)]
    assert _parse_order_pairs("7:0") == [(7, 0)]


def test_parse_order_pairs_invalid():
    assert _parse_order_pairs("") is None
    assert _parse_order_pairs("3-1") is None
    assert _parse_order_pairs("a:1") is None
    assert _parse_order_pairs("1:x") is None
    assert _parse_order_pairs("1:2, oops") is None


# users pagination + last_activity


async def test_touch_sets_last_activity(session_factory):
    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.touch(1, username="u1")
        await session.commit()
        user = await repo.get(1)
        assert user is not None
        assert user.last_activity is not None


async def test_users_get_page_sorts_by_last_activity_desc(session_factory):
    from datetime import UTC, datetime, timedelta

    async with session_factory() as session:
        repo = UserRepository(session)
        await repo.touch(1, username="older")
        await repo.touch(2, username="newer")
        await session.commit()
        # backdate user 1 so user 2 (touched later) sorts first
        user1 = await repo.get(1)
        assert user1 is not None
        user1.last_activity = datetime.now(UTC) - timedelta(hours=2)
        await session.commit()

        page = await repo.get_page(0, 10)
        assert [u.id for u in page] == [2, 1]
        assert await repo.count() == 2


# chats pagination


async def test_chats_get_page_and_counts(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        for i in range(5):
            await repo.add_or_update(
                chat_id=-2000 - i,
                exact_name=f"Chat {i:02d}",
                join_link="",
                added_by=7 if i < 2 else None,
            )
        await session.commit()

        assert await repo.count() == 5
        assert await repo.count_by_added_by(7) == 2
        page = await repo.get_page(0, 2)
        assert [c.exact_name for c in page] == ["Chat 00", "Chat 01"]
        page2 = await repo.get_page(2, 2)
        assert [c.exact_name for c in page2] == ["Chat 02", "Chat 03"]


async def test_remove_by_name_returns_bool(session_factory):
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(chat_id=-3000, exact_name="Gone", join_link="")
        await session.commit()
        assert await repo.remove_by_name("Gone") is True
        assert await repo.remove_by_name("Gone") is False
        assert await repo.remove_by_chat_id(-3000) is False
