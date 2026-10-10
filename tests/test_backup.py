"""Tests for the automatic local DB backup service."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import time

from bot.config import Settings
from bot.db.repo.chats import ChatRepository
from bot.services.backup import create_backup, is_due


def _settings(db_path, backup_dir, **kwargs) -> Settings:
    return Settings(  # type: ignore[call-arg]
        bot_token="1234567890:AAA-test",
        bot_name="testbot",
        main_channel_id=-100,
        db_path=db_path,
        backup_dir=backup_dir,
        **kwargs,
    )


async def test_create_backup_snapshots_live_db(session_factory, tmp_path):
    async with session_factory() as session:
        repo = ChatRepository(session)
        await repo.add_or_update(chat_id=-100123, exact_name="Чат", join_link="https://t.me/+abc")
        await session.commit()

    backup_dir = tmp_path / "backups"
    settings = _settings(tmp_path / "test.sqlite", backup_dir)

    out = await create_backup(settings)
    assert out.exists()
    assert out.parent == backup_dir
    with sqlite3.connect(out) as con:
        rows = con.execute("SELECT exact_name, join_link FROM SavedChats").fetchall()
    assert rows == [("Чат", "https://t.me/+abc")]


async def test_create_backup_prunes_to_keep(session_factory, tmp_path):
    backup_dir = tmp_path / "backups"
    settings = _settings(tmp_path / "test.sqlite", backup_dir, backup_keep=2)

    created = []
    for i in range(4):
        out = await create_backup(settings)
        os.utime(out, (1000 + i, 1000 + i))
        created.append(out)
        await asyncio.sleep(1.1)  # unique timestamped filename per second

    remaining = set(backup_dir.glob("db-*.sqlite"))
    assert remaining == set(created[-2:])


async def test_is_due(session_factory, tmp_path):
    backup_dir = tmp_path / "backups"
    settings = _settings(tmp_path / "test.sqlite", backup_dir, backup_interval_hours=24)

    assert is_due(settings) is True  # no snapshots yet

    out = await create_backup(settings)
    assert is_due(settings) is False  # fresh snapshot

    old = time.time() - 25 * 3600
    os.utime(out, (old, old))
    assert is_due(settings) is True
