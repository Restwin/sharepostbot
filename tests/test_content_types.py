"""Tests for the republish content-type whitelist."""

from __future__ import annotations

import datetime

import pytest
from aiogram.types import (
    Animation,
    Audio,
    Chat,
    Contact,
    Document,
    Location,
    Message,
    PhotoSize,
    Poll,
    PollOption,
    Sticker,
    User,
    Video,
    VideoNote,
    Voice,
)

from bot.services.content_types import (
    NON_ANONYMOUS_POLL_REPLY,
    UNSUPPORTED_REPLY,
    classify_content,
    unsupported_reply,
)


def _msg(**content) -> Message:
    return Message(
        message_id=1,
        date=datetime.datetime.now(),
        chat=Chat(id=1, type="private"),
        from_user=User(id=1, is_bot=False, first_name="A"),
        **content,
    )


def _poll(anonymous: bool) -> Poll:
    return Poll(
        id="p1",
        question="Q?",
        options=[PollOption(persistent_id="o1", text="A", voter_count=0)],
        total_voter_count=0,
        is_closed=False,
        is_anonymous=anonymous,
        type="regular",
        allows_multiple_answers=False,
        allows_revoting=False,
        members_only=False,
    )


def test_classify_text():
    assert classify_content(_msg(text="hello")) == "text"


def test_classify_photo():
    assert (
        classify_content(
            _msg(photo=[PhotoSize(file_id="f", file_unique_id="u", width=10, height=10)])
        )
        == "photo"
    )


def test_classify_video():
    assert (
        classify_content(
            _msg(video=Video(file_id="f", file_unique_id="u", width=10, height=10, duration=1))
        )
        == "video"
    )


def test_classify_document():
    assert classify_content(_msg(document=Document(file_id="f", file_unique_id="u"))) == "document"


def test_classify_anonymous_poll():
    assert classify_content(_msg(poll=_poll(True))) == "poll"


def test_classify_non_anonymous_poll_is_unsupported():
    assert classify_content(_msg(poll=_poll(False))) is None
    assert unsupported_reply(_msg(poll=_poll(False))) == NON_ANONYMOUS_POLL_REPLY


@pytest.mark.parametrize(
    "content",
    [
        dict(
            sticker=Sticker(
                file_id="f",
                file_unique_id="u",
                type="regular",
                width=10,
                height=10,
                is_animated=False,
                is_video=False,
            )
        ),
        dict(audio=Audio(file_id="f", file_unique_id="u", duration=1)),
        dict(voice=Voice(file_id="f", file_unique_id="u", duration=1)),
        dict(video_note=VideoNote(file_id="f", file_unique_id="u", length=10, duration=1)),
        dict(animation=Animation(file_id="f", file_unique_id="u", width=10, height=10, duration=1)),
        dict(contact=Contact(phone_number="+79123456789", first_name="X")),
        dict(location=Location(latitude=1.0, longitude=2.0)),
    ],
)
def test_classify_unsupported_content_returns_none(content):
    assert classify_content(_msg(**content)) is None
    assert unsupported_reply(_msg(**content)) == UNSUPPORTED_REPLY
