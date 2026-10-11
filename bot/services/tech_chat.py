"""Tech-chat sink: forward selected log events to admin Telegram chats.

What leaves the process:
- events at or above `log_chat_level` as the "errors" category;
- events logged with `to_tech="<category>"` (system/admin/business) when
  that category is enabled in `log_chat_events`.

`TechChatSink` plugs into structlog as an extra processor after secret
redaction and exception rendering, keeps a bounded queue and a background
sender that rate-limits per chat and honours 429 retry_after. Delivery is
best-effort: logging must never break the bot, so send failures only produce
local log records.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from bot.logging_setup import get_logger

_log = get_logger("bot.tech_chat")
_OWN_LOGGER_PREFIX = "bot.tech_chat"

CATEGORIES = ("errors", "system", "admin", "business")

_LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40, "critical": 50}
_LEVEL_EMOJI = {"debug": "🐛", "info": "ℹ️", "warning": "⚠️", "error": "🔥", "critical": "🚨"}
_META_KEYS = frozenset({"level", "timestamp", "logger", "event", "to_tech", "exception"})
_FIELD_ORDER = ("chat_id", "user_id", "update_id", "path", "error", "error_type")


def classify(
    event_dict: dict[str, Any],
    *,
    min_level: str,
    categories: set[str],
) -> str | None:
    """Return the delivery category for this event, or None to keep it local."""
    if str(event_dict.get("logger", "")).startswith(_OWN_LOGGER_PREFIX):
        return None  # never forward the sink's own delivery errors
    explicit = event_dict.get("to_tech")
    if explicit is not None and explicit is not False:
        category = "system" if explicit is True else str(explicit)
        return category if category in categories else None
    level = str(event_dict.get("level", "")).lower()
    if "errors" in categories and _LEVELS.get(level, 0) >= _LEVELS.get(min_level, 40):
        return "errors"
    return None


def format_event(event_dict: dict[str, Any], category: str) -> str:
    """Render one log event as a compact plain-text message."""
    level = str(event_dict.get("level", "info")).lower()
    logger_name = event_dict.get("logger", "")
    lines = [
        f"{_LEVEL_EMOJI.get(level, '•')} {level.upper()} {logger_name} [{category}]",
        str(event_dict.get("event", "log")),
    ]

    extras = {key: value for key, value in event_dict.items() if key not in _META_KEYS}
    ordered = [key for key in _FIELD_ORDER if key in extras]
    ordered += sorted(key for key in extras if key not in _FIELD_ORDER)
    if ordered:
        lines.append("  ".join(f"{key}={extras[key]}" for key in ordered))

    exception = event_dict.get("exception")
    if exception:
        lines.append(str(exception).rstrip())
    return "\n".join(lines)


def chunk_text(text: str, limit: int) -> list[str]:
    """Split into chunks of at most `limit` chars, preferring line breaks."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines() or [""]:
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if not current:
            current = line
        elif len(current) + 1 + len(line) <= limit:
            current = f"{current}\n{line}"
        else:
            chunks.append(current)
            current = line
    if current or not chunks:
        chunks.append(current)
    return chunks


@dataclass
class _Seen:
    window_started: float
    repeats: int = 0


class _Deduper:
    """Suppress duplicate texts inside a sliding window, counting repeats."""

    def __init__(self, window: float, max_entries: int = 512) -> None:
        self._window = window
        self._max_entries = max_entries
        self._seen: dict[str, _Seen] = {}

    def check(self, text: str, now: float | None = None) -> tuple[bool, int]:
        """Return (send_now, repeats_since_previous_send)."""
        current = time.monotonic() if now is None else now
        key = hashlib.sha256(text.encode()).hexdigest()[:16]
        seen = self._seen.get(key)
        if seen is not None and current - seen.window_started < self._window:
            seen.repeats += 1
            return False, seen.repeats
        repeats = seen.repeats if seen is not None else 0
        if len(self._seen) >= self._max_entries:
            self._prune(current)
            while len(self._seen) >= self._max_entries:
                oldest = min(self._seen, key=lambda key: self._seen[key].window_started)
                del self._seen[oldest]
        self._seen[key] = _Seen(window_started=current)
        return True, repeats

    def _prune(self, now: float) -> None:
        stale = [
            key for key, seen in self._seen.items() if now - seen.window_started >= self._window
        ]
        for key in stale:
            del self._seen[key]


class TechChatSink:
    """structlog processor plus best-effort background sender for tech chats."""

    def __init__(
        self,
        chat_ids: Sequence[int],
        *,
        level: str = "ERROR",
        categories: Iterable[str] = CATEGORIES,
        queue_size: int = 200,
        dedup_window: float = 60.0,
        min_interval: float = 1.0,
        chunk_limit: int = 3500,
        max_chunks: int = 5,
    ) -> None:
        self._chat_ids = tuple(chat_ids)
        self._categories = {category for category in categories if category in CATEGORIES}
        self._min_level = level
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=queue_size)
        self._dedup = _Deduper(dedup_window)
        self._min_interval = min_interval
        self._chunk_limit = chunk_limit
        self._max_chunks = max_chunks
        self._bot: Bot | None = None
        self._task: asyncio.Task[None] | None = None
        self._last_sent: dict[int, float] = {}

    @property
    def enabled(self) -> bool:
        return bool(self._chat_ids) and bool(self._categories)

    def processor(
        self,
        logger: Any,
        method_name: str,
        event_dict: dict[str, Any],
    ) -> dict[str, Any]:
        """structlog processor hook. Must never raise into the logging chain."""
        try:
            if self.enabled:
                category = classify(
                    event_dict, min_level=self._min_level, categories=self._categories
                )
                if category is not None:
                    text = format_event(event_dict, category)
                    send_now, repeats = True, 0
                    if category == "errors":
                        send_now, repeats = self._dedup.check(text)
                    if send_now:
                        if repeats:
                            text = f"{text}\n…повторов подряд: {repeats}"
                        self._enqueue(text)
        except Exception:
            logging.getLogger(__name__).warning("tech chat sink failed", exc_info=True)
        return event_dict

    def attach(self, bot: Bot) -> None:
        """Start the background sender (no-op when disabled or already running)."""
        if not self.enabled or self._task is not None:
            return
        self._bot = bot
        self._task = asyncio.create_task(self._run(), name="tech-chat-sink")

    async def aclose(self, flush_timeout: float = 5.0) -> None:
        """Flush pending messages (bounded by `flush_timeout`) and stop the sender."""
        task = self._task
        if task is None:
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._queue.join(), flush_timeout)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        self._task = None
        self._bot = None

    def _enqueue(self, text: str) -> None:
        if self._queue.full():
            # drop the oldest event: fresh evidence beats stale evidence
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
                self._queue.task_done()
        with contextlib.suppress(asyncio.QueueFull):
            self._queue.put_nowait(text)

    async def _run(self) -> None:
        while True:
            text = await self._queue.get()
            try:
                await self._deliver(text)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _log.warning("tech_chat_delivery_failed", error=str(exc))
            finally:
                self._queue.task_done()

    async def _deliver(self, text: str) -> None:
        bot = self._bot
        if bot is None:
            return
        chunks = chunk_text(text, self._chunk_limit)
        if len(chunks) > self._max_chunks:
            dropped = len(chunks) - self._max_chunks
            chunks = chunks[: self._max_chunks]
            chunks[-1] += f"\n…обрезано ещё {dropped} ч."
        for chat_id in self._chat_ids:
            await self._throttle(chat_id)
            for chunk in chunks:
                await self._send(bot, chat_id, chunk)

    async def _throttle(self, chat_id: int) -> None:
        wait = self._last_sent.get(chat_id, 0.0) + self._min_interval - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_sent[chat_id] = time.monotonic()

    async def _send(self, bot: Bot, chat_id: int, text: str) -> None:
        # parse_mode=None keeps log text immune to HTML/Markdown escaping
        # (hand-rolled escaping was the legacy bot's #1 bug).
        try:
            await bot.send_message(chat_id, text, parse_mode=None)
        except TelegramRetryAfter as exc:
            await asyncio.sleep(exc.retry_after)
            try:
                await bot.send_message(chat_id, text, parse_mode=None)
            except Exception as retry_exc:
                _log.warning("tech_chat_send_failed", chat_id=chat_id, error=str(retry_exc))
        except (TelegramForbiddenError, TelegramBadRequest):
            _log.warning("tech_chat_unavailable", chat_id=chat_id)
        except Exception as exc:
            _log.warning("tech_chat_send_failed", chat_id=chat_id, error=str(exc))
