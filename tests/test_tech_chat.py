"""Tech-chat sink: classification, formatting, chunking, dedup."""

from __future__ import annotations

from bot.services.tech_chat import TechChatSink, _Deduper, chunk_text, classify, format_event


class _StubBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str, parse_mode: object = None) -> None:
        self.sent.append((chat_id, text))


def test_classify_error_level_gives_errors_category():
    event = {"level": "error", "logger": "bot.repost", "event": "repost_publish_failed"}
    assert classify(event, min_level="ERROR", categories={"errors"}) == "errors"


def test_classify_info_level_stays_local():
    event = {"level": "info", "logger": "bot.repost", "event": "repost_ok"}
    assert classify(event, min_level="ERROR", categories={"errors"}) is None


def test_classify_explicit_category_bypasses_level():
    event = {"level": "info", "logger": "bot.admin", "to_tech": "admin"}
    assert classify(event, min_level="ERROR", categories={"admin"}) == "admin"


def test_classify_disabled_category_is_skipped():
    event = {"level": "error", "logger": "bot.admin", "to_tech": "admin"}
    assert classify(event, min_level="ERROR", categories={"errors"}) is None


def test_classify_ignores_sink_own_logger():
    event = {"level": "error", "logger": "bot.tech_chat", "event": "send_failed"}
    assert classify(event, min_level="ERROR", categories={"errors"}) is None


def test_classify_true_means_system_category():
    event = {"level": "info", "logger": "bot.main", "to_tech": True}
    assert classify(event, min_level="ERROR", categories={"system"}) == "system"


def test_format_event_contains_context_and_exception():
    event = {
        "level": "error",
        "logger": "bot.repost",
        "event": "repost_publish_failed",
        "chat_id": -100,
        "user_id": 42,
        "exception": "Traceback (most recent call last):\nValueError: boom",
    }
    text = format_event(event, "errors")
    assert "ERROR bot.repost [errors]" in text
    assert "repost_publish_failed" in text
    assert "chat_id=-100" in text
    assert "ValueError: boom" in text


def test_chunk_text_prefers_line_breaks():
    text = "\n".join(f"line-{i:03d}-{'x' * 40}" for i in range(200))
    chunks = chunk_text(text, limit=500)
    assert all(len(chunk) <= 500 for chunk in chunks)
    assert "\n".join(chunks) == text


def test_chunk_text_hard_cuts_giant_line():
    chunks = chunk_text("a" * 1200, limit=500)
    assert [len(chunk) for chunk in chunks] == [500, 500, 200]


def test_deduper_suppresses_and_counts_repeats():
    dedup = _Deduper(window=60.0)
    assert dedup.check("boom", now=0.0) == (True, 0)
    assert dedup.check("boom", now=1.0) == (False, 1)
    assert dedup.check("boom", now=2.0) == (False, 2)
    assert dedup.check("boom", now=61.0) == (True, 2)


def test_deduper_prunes_stale_entries():
    dedup = _Deduper(window=10.0, max_entries=2)
    for index in range(5):
        dedup.check(f"event-{index}", now=float(index))
    assert dedup.check("new-event", now=100.0) == (True, 0)


async def test_sink_delivers_errors_and_drops_the_rest():
    sink = TechChatSink([-100], min_interval=0.0)
    bot = _StubBot()
    sink.attach(bot)
    error_event = {"level": "error", "logger": "bot.repost", "event": "boom"}
    assert sink.processor(None, "error", dict(error_event))
    sink.processor(None, "error", dict(error_event))  # duplicate -> deduped
    sink.processor(None, "info", {"level": "info", "logger": "bot.x", "event": "noise"})
    await sink.aclose()
    assert len(bot.sent) == 1
    assert "boom" in bot.sent[0][1]
