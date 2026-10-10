"""Automatic local backups of the SQLite database.

Rotating timestamped snapshots via `VACUUM INTO`, SQLite's canonical way to
copy a live WAL-mode database consistently without stopping writes. Snapshots
land in `BACKUP_DIR` (default ./data/backups); only the newest `BACKUP_KEEP`
files are kept. Nothing is sent to Telegram: `/backup_db` covers the rare
manual offsite copy.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from bot.config import Settings
from bot.logging_setup import get_logger

_log = get_logger("bot.backup")

_BACKUP_GLOB = "db-*.sqlite"


def _latest_backup(backup_dir: Path) -> Path | None:
    files = sorted(backup_dir.glob(_BACKUP_GLOB), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


def is_due(settings: Settings) -> bool:
    """True when there is no snapshot newer than the configured interval."""
    latest = _latest_backup(settings.backup_dir)
    if latest is None:
        return True
    age = time.time() - latest.stat().st_mtime
    return age >= settings.backup_interval_hours * 3600


async def create_backup(settings: Settings) -> Path:
    """Snapshot the DB into BACKUP_DIR (timestamped) and prune old snapshots."""
    if not settings.db_path.exists():
        raise FileNotFoundError(f"database file not found: {settings.db_path}")

    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = settings.backup_dir / f"db-{stamp}.sqlite"

    async with aiosqlite.connect(settings.db_path) as db:
        await db.execute("VACUUM INTO ?", (str(target),))

    _prune(settings.backup_dir, keep=settings.backup_keep)
    _log.info("backup_created", path=str(target))
    return target


def _prune(backup_dir: Path, *, keep: int) -> None:
    """Delete the oldest snapshots, keeping the newest `keep` files."""
    files = sorted(backup_dir.glob(_BACKUP_GLOB), key=lambda p: p.stat().st_mtime)
    for old in files[:-keep]:
        try:
            old.unlink()
            _log.info("backup_pruned", path=str(old))
        except OSError as exc:
            _log.warning("backup_prune_failed", path=str(old), error=str(exc))


async def backup_loop(settings: Settings) -> None:
    """Periodic backup task, runs forever until cancelled.

    The due-check (instead of a bare sleep) guarantees a fresh snapshot
    survives bot restarts, while a crash-loop cannot flood the folder: a second
    start sees a fresh snapshot and skips it.
    """
    interval = settings.backup_interval_hours * 3600
    while True:
        try:
            if is_due(settings):
                await create_backup(settings)
        except Exception:
            _log.exception("backup_failed")
        await asyncio.sleep(interval)
