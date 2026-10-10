"""Database initialization: create tables, set SQLite pragmas, seed defaults.

This module is the single source of truth for the schema: `create_all` creates
missing tables (idempotent), guarded `ALTER`/`DROP` statements below cover
column changes on existing DBs, and default categories are seeded when the
table is empty.

WAL, busy_timeout and foreign_keys are applied to every new connection.
"""

from __future__ import annotations

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from bot import texts
from bot.db.models import Base

# Columns added after the initial deployment: `create_all` creates missing
# tables but never alters existing ones, so they are backfilled here with
# guarded `ALTER TABLE ... ADD COLUMN` (no-op once present). Add an entry when
# a new column is introduced, alongside the model definition.
_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "Users": {"blocked_by": "BIGINT", "last_activity": "DATETIME"},
    "SavedChats": {
        "is_blocked": "BOOLEAN NOT NULL DEFAULT 0",
        "block_reason": "VARCHAR NOT NULL DEFAULT ''",
        "blocked_by": "BIGINT",
        "link_source": "VARCHAR(8) NOT NULL DEFAULT 'bot'",
        "join_approval": "VARCHAR(8) NOT NULL DEFAULT 'open'",
    },
    "PublishedPosts": {
        "channel_message_ids": "VARCHAR NOT NULL DEFAULT ''",
        "is_deleted": "BOOLEAN NOT NULL DEFAULT 0",
        "source_message_id": "BIGINT",
        "kind": "VARCHAR(16) NOT NULL DEFAULT 'text'",
        "body_html": "TEXT NOT NULL DEFAULT ''",
        "file_id": "VARCHAR NOT NULL DEFAULT ''",
        "sig_text": "TEXT NOT NULL DEFAULT ''",
        "source_edited": "BOOLEAN NOT NULL DEFAULT 0",
        "source_media_changed": "BOOLEAN NOT NULL DEFAULT 0",
    },
}

# Columns removed from the model after the initial deployment. SQLite keeps
# the old column (`create_all` never drops), and a stale `NOT NULL` column
# with no default breaks every INSERT, so drop them idempotently here.
_DROP_COLUMNS: dict[str, list[str]] = {
    "SavedChats": ["welcome_message"],
}


async def init_db(engine: AsyncEngine) -> None:
    """Create tables if missing and apply SQLite pragmas."""

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragmas(dbapi_conn, _record):  # type: ignore[no-untyped-def]
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Ensure WAL is applied immediately (the connect listener runs on first checkout).
        await conn.execute(text("PRAGMA journal_mode=WAL"))
        await _drop_columns(conn)
        await _ensure_columns(conn)
        await _seed_post_categories(conn)


async def _drop_columns(conn: AsyncConnection) -> None:
    """Idempotently drop columns removed from the model after deployment."""
    for table, columns in _DROP_COLUMNS.items():
        existing = {
            row[1] for row in (await conn.execute(text(f'PRAGMA table_info("{table}")'))).fetchall()
        }
        for column in columns:
            if column in existing:
                await conn.execute(text(f'ALTER TABLE "{table}" DROP COLUMN "{column}"'))


async def _ensure_columns(conn: AsyncConnection) -> None:
    """Idempotently add columns introduced after an existing DB was created."""
    for table, columns in _ADDITIVE_COLUMNS.items():
        existing = {
            row[1] for row in (await conn.execute(text(f'PRAGMA table_info("{table}")'))).fetchall()
        }
        for column, ddl in columns.items():
            if column not in existing:
                await conn.execute(text(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {ddl}'))


async def _seed_post_categories(conn: AsyncConnection) -> None:
    """Seed default post categories when the table is empty."""
    result = await conn.execute(text("SELECT COUNT(*) FROM PostCategories"))
    if (result.scalar_one() or 0) > 0:
        return
    for idx, name in enumerate(texts.DEFAULT_POST_CATEGORIES):
        await conn.execute(
            text(
                "INSERT INTO PostCategories (name, display_order, is_active) "
                "VALUES (:name, :order, 1)"
            ),
            {"name": name, "order": idx},
        )
