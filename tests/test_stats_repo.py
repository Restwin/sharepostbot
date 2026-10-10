"""Tests for PostStatRepository."""

from __future__ import annotations

from bot.db.repo.stats import PostStatRepository


async def _add(repo: PostStatRepository, author_id: int, category: str) -> None:
    await repo.add(
        author_id=author_id,
        author_name=f"user{author_id}",
        source="pm",
        category=category,
        preview=f"preview {author_id}",
    )


async def test_add_and_get_recent_orders_newest_first(session_factory):
    async with session_factory() as session:
        repo = PostStatRepository(session)
        await _add(repo, 1, "Другое")
        await _add(repo, 2, "Недвижимость")
        await session.commit()

    async with session_factory() as session:
        repo = PostStatRepository(session)
        recent = await repo.get_recent(10)
        assert len(recent) == 2
        assert recent[0].author_id == 2  # newest first
        assert await repo.count() == 2


async def test_count_by_category(session_factory):
    async with session_factory() as session:
        repo = PostStatRepository(session)
        await _add(repo, 1, "Другое")
        await _add(repo, 2, "Другое")
        await _add(repo, 3, "Недвижимость")
        await session.commit()

    async with session_factory() as session:
        repo = PostStatRepository(session)
        rows = await repo.count_by_category()
        counts = {name: cnt for name, cnt in rows}
        assert counts["Другое"] == 2
        assert counts["Недвижимость"] == 1


async def test_count_by_user(session_factory):
    async with session_factory() as session:
        repo = PostStatRepository(session)
        await _add(repo, 1, "Другое")
        await _add(repo, 1, "Недвижимость")
        await _add(repo, 2, "Другое")
        await session.commit()

    async with session_factory() as session:
        repo = PostStatRepository(session)
        rows = await repo.count_by_user()
        counts = {uid: cnt for uid, _name, cnt in rows}
        assert counts[1] == 2
        assert counts[2] == 1


async def test_get_by_author_and_count_by_author(session_factory):
    async with session_factory() as session:
        repo = PostStatRepository(session)
        await _add(repo, 1, "Другое")
        await _add(repo, 2, "Недвижимость")
        await _add(repo, 1, "Поиск специалиста")
        await session.commit()

    async with session_factory() as session:
        repo = PostStatRepository(session)
        assert await repo.count_by_author(1) == 2
        posts = await repo.get_by_author(1)
        assert len(posts) == 2
        assert all(p.author_id == 1 for p in posts)
        # newest first
        assert posts[0].category == "Поиск специалиста"
        assert await repo.count_by_author(999) == 0


async def test_mention_source_fields_are_stored(session_factory):
    async with session_factory() as session:
        repo = PostStatRepository(session)
        await repo.add(
            author_id=1,
            author_name="Alice",
            source="mention",
            category="Поиск специалиста",
            preview="нужен сантехник",
            source_chat_id=-100123,
            source_chat_name="ФЗ сообщество",
        )
        await session.commit()

    async with session_factory() as session:
        repo = PostStatRepository(session)
        recent = await repo.get_recent(1)
        assert recent[0].source == "mention"
        assert recent[0].source_chat_id == -100123
        assert recent[0].source_chat_name == "ФЗ сообщество"


async def test_channel_message_ids_stored(session_factory):
    async with session_factory() as session:
        repo = PostStatRepository(session)
        await repo.add(
            author_id=1,
            author_name="Alice",
            source="pm",
            category="Другое",
            preview="x",
            channel_message_ids="111,222,333",
        )
        await session.commit()

    async with session_factory() as session:
        repo = PostStatRepository(session)
        post = (await repo.get_recent(1))[0]
        assert post.channel_message_ids == "111,222,333"


async def test_mark_deleted_excludes_from_all_queries(session_factory):
    async with session_factory() as session:
        repo = PostStatRepository(session)
        await _add(repo, 1, "Другое")
        await _add(repo, 2, "Недвижимость")
        await session.commit()
        p1 = (await repo.get_by_author(1))[0]
        repo.mark_deleted(p1)
        await session.commit()

    async with session_factory() as session:
        repo = PostStatRepository(session)
        assert await repo.count() == 1
        recent = await repo.get_recent(10)
        assert len(recent) == 1
        assert recent[0].author_id == 2
        assert await repo.count_by_author(1) == 0
        assert dict(await repo.count_by_category()) == {"Недвижимость": 1}
        assert dict((uid, cnt) for uid, _n, cnt in await repo.count_by_user()) == {2: 1}


async def test_get_by_id(session_factory):
    async with session_factory() as session:
        repo = PostStatRepository(session)
        await _add(repo, 1, "Другое")
        await session.commit()
        post_id = (await repo.get_recent(1))[0].id
        assert (await repo.get_by_id(post_id)).author_id == 1
        assert await repo.get_by_id(999_999) is None


async def test_add_stores_source_snapshot(session_factory):
    async with session_factory() as session:
        repo = PostStatRepository(session)
        await repo.add(
            author_id=1,
            author_name="Alice",
            source="pm",
            category="Другое",
            preview="x",
            source_chat_id=42,
            source_message_id=777,
            kind="text",
            body_html="hello",
            file_id="",
            sig_text="— Alice",
        )
        await session.commit()

    async with session_factory() as session:
        repo = PostStatRepository(session)
        post = (await repo.get_recent(1))[0]
        assert post.source_chat_id == 42
        assert post.source_message_id == 777
        assert post.kind == "text"
        assert post.body_html == "hello"
        assert post.sig_text == "— Alice"


async def test_update_source_content_marks_edited(session_factory):
    async with session_factory() as session:
        repo = PostStatRepository(session)
        await _add(repo, 1, "Другое")
        await session.commit()
        post = (await repo.get_recent(1))[0]
        assert post.source_edited is False
        repo.update_source_content(post, body_html="updated", file_id="")
        await session.commit()

    async with session_factory() as session:
        repo = PostStatRepository(session)
        post = (await repo.get_recent(1))[0]
        assert post.source_edited is True
        assert post.body_html == "updated"


async def test_update_source_content_marks_media_changed(session_factory):
    async with session_factory() as session:
        repo = PostStatRepository(session)
        await _add(repo, 1, "Другое")
        await session.commit()
        post = (await repo.get_recent(1))[0]
        assert post.source_media_changed is False
        # caption-only edit: file_id unchanged, media change not flagged
        repo.update_source_content(post, body_html="new caption", file_id="file_AAA")
        await session.commit()

    async with session_factory() as session:
        repo = PostStatRepository(session)
        post = (await repo.get_recent(1))[0]
        assert post.source_media_changed is False

    async with session_factory() as session:
        repo = PostStatRepository(session)
        post = (await repo.get_recent(1))[0]
        # media replaced: file_id differs, media change flagged
        repo.update_source_content(
            post, body_html="new caption", file_id="file_BBB", media_changed=True
        )
        await session.commit()

    async with session_factory() as session:
        repo = PostStatRepository(session)
        post = (await repo.get_recent(1))[0]
        assert post.source_media_changed is True


async def test_clear_source_edited_resets_media_changed(session_factory):
    async with session_factory() as session:
        repo = PostStatRepository(session)
        await _add(repo, 1, "Другое")
        await session.commit()
        post = (await repo.get_recent(1))[0]
        repo.update_source_content(post, body_html="x", file_id="file_BBB", media_changed=True)
        assert post.source_media_changed is True
        repo.clear_source_edited(post)
        assert post.source_edited is False
        assert post.source_media_changed is False
        await session.commit()


async def test_get_by_source_and_deleted_exclusion(session_factory):
    async with session_factory() as session:
        repo = PostStatRepository(session)
        await repo.add(
            author_id=1,
            author_name="A",
            source="mention",
            category="Другое",
            preview="x",
            source_chat_id=-1001,
            source_message_id=10,
        )
        await repo.add(
            author_id=2,
            author_name="B",
            source="pm",
            category="Другое",
            preview="y",
            source_chat_id=-1001,
            source_message_id=10,
        )
        await session.commit()

    async with session_factory() as session:
        repo = PostStatRepository(session)
        matches = await repo.get_by_source(-1001, 10)
        assert {p.author_id for p in matches} == {1, 2}

    # after marking one deleted, only the other matches
    async with session_factory() as session:
        repo = PostStatRepository(session)
        post = (await repo.get_by_author(1))[0]
        repo.mark_deleted(post)
        await session.commit()

    async with session_factory() as session:
        repo = PostStatRepository(session)
        matches = await repo.get_by_source(-1001, 10)
        assert {p.author_id for p in matches} == {2}
