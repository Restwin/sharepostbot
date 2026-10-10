"""Tests for post_builder: signature HTML, body rendering, composition."""

from __future__ import annotations

from aiogram.types import Chat, Message, MessageEntity, User

from bot.db.models import SavedChat
from bot.services.post_builder import (
    build_signature,
    category_line,
    compose_html,
    render_message_body,
)


def _user(
    uid: int, first: str = "Alice", username: str | None = None, last: str | None = None
) -> User:
    return User(id=uid, is_bot=False, first_name=first, last_name=last, username=username)


def _supergroup(chat_id: int, title: str = "Source Chat", username: str | None = None) -> Chat:
    return Chat(id=chat_id, type="supergroup", title=title, username=username)


def _text_message(
    text: str,
    entities: list[MessageEntity] | None = None,
    chat_id: int = -1001,
    user_id: int = 42,
) -> Message:
    return Message(
        message_id=1,
        date=1,
        chat=_supergroup(chat_id),
        from_user=_user(user_id),
        text=text,
        entities=entities,
    )


def _photo_message(
    caption: str,
    caption_entities: list[MessageEntity] | None = None,
    chat_id: int = -1001,
    user_id: int = 42,
) -> Message:
    from aiogram.types import PhotoSize

    return Message(
        message_id=2,
        date=1,
        chat=_supergroup(chat_id),
        from_user=_user(user_id),
        photo=[PhotoSize(file_id="x", file_unique_id="x", width=100, height=100)],
        caption=caption,
        caption_entities=caption_entities,
    )


# --- build_signature ---


def test_signature_private_chat_only_author_mention():
    user = _user(42, "Bob")
    chat = Chat(id=42, type="private", first_name="Bob")
    sig = build_signature(author=user, source_chat=chat, saved_chat=None, message_id_in_source=None)
    assert "tg://user?id=42" in sig.text
    assert "Bob" in sig.text
    assert "из ЛС" in sig.text  # PM post uses "из ЛС" instead of "пост"
    assert "пост" not in sig.text


def test_signature_public_chat_uses_username_link():
    # no message id: only the @username link, no "пост" message link
    user = _user(1, "Carol")
    chat = _supergroup(-100123, title="Public Group", username="publicgroup")
    sig = build_signature(author=user, source_chat=chat, saved_chat=None, message_id_in_source=None)
    assert "https://t.me/publicgroup" in sig.text
    assert "Public Group" in sig.text
    assert "пост" not in sig.text


def test_signature_supergroup_has_both_links():
    # saved join link and a message id: chat link on the name, "пост" on the message
    user = _user(7, "Dave")
    chat = _supergroup(-100456, title="Secret Group")
    saved = SavedChat(
        id=1, chat_id=-100456, exact_name="Secret Group", join_link="https://t.me/+abc"
    )
    sig = build_signature(author=user, source_chat=chat, saved_chat=saved, message_id_in_source=99)
    assert "https://t.me/+abc" in sig.text  # join link on the chat name
    assert "https://t.me/c/456/99" in sig.text  # message link on "пост"
    assert "Secret Group" in sig.text
    assert "пост" in sig.text


def test_signature_no_link_falls_back_to_quoted_title():
    user = _user(9, "Eve")
    chat = _supergroup(-100789, title="Unknown Group")
    sig = build_signature(author=user, source_chat=chat, saved_chat=None, message_id_in_source=None)
    assert "«Unknown Group»" in sig.text
    assert "https://t.me/+" not in sig.text


def test_signature_html_escapes_author_name():
    user = _user(11, first="<script>alert(1)</script>")
    chat = _supergroup(-1001, title="X")
    sig = build_signature(author=user, source_chat=chat, saved_chat=None, message_id_in_source=1)
    assert "<script>" not in sig.text
    assert "&lt;script&gt;" in sig.text


def test_signature_handles_author_with_last_name():
    user = _user(13, first="Frank", last="Miller")
    chat = _supergroup(-1002, title="Y")
    sig = build_signature(author=user, source_chat=chat, saved_chat=None, message_id_in_source=1)
    assert "Frank Miller" in sig.text


# --- render_message_body ---


def test_render_text_message_preserves_bold_and_link_entities():
    msg = _text_message(
        text="Hello bold and link here",
        entities=[
            MessageEntity(type="bold", offset=6, length=4),
            MessageEntity(type="text_link", offset=11, length=4, url="https://x.com"),
        ],
    )
    html = render_message_body(msg)
    assert "<b>bold</b>" in html
    assert '<a href="https://x.com">' in html


def test_render_caption_preserves_entities():
    msg = _photo_message(
        caption="cap with bold text",
        caption_entities=[MessageEntity(type="bold", offset=9, length=4)],
    )
    html = render_message_body(msg)
    assert "<b>bold</b>" in html


def test_render_empty_message_returns_empty():
    msg = Message(message_id=1, date=1, chat=_supergroup(-1), from_user=_user(1))
    assert render_message_body(msg) == ""


# --- category + composition ---


def test_category_line_renders_italic_and_escapes():
    assert category_line("Движуха ФЗ сообщества") == "<i>Движуха ФЗ сообщества</i>"
    assert category_line("<Сам> & Реклама") == "<i>&lt;Сам&gt; &amp; Реклама</i>"


def test_compose_html_with_category_and_post_link():
    sig = 'Alice из <a href="https://t.me/+abc">Чат</a> · <a href="https://t.me/c/1/2">пост</a>'
    result = compose_html("Тело", sig, "Недвижимость")
    assert result == (
        'Тело\n\n— Alice из <a href="https://t.me/+abc">Чат</a> '
        '(<i>Недвижимость</i> · <a href="https://t.me/c/1/2">пост</a>)'
    )


def test_compose_html_pm_with_category():
    result = compose_html("Тело", "Alice · из ЛС", "Запросы и просьбы")
    assert result == "Тело\n\n— Alice (<i>Запросы и просьбы</i> · из ЛС)"


def test_compose_html_with_category_no_post_link():
    result = compose_html("Тело", "Alice из «Чат»", "Недвижимость")
    assert result == "Тело\n\n— Alice из «Чат» (<i>Недвижимость</i>)"


def test_compose_html_without_category():
    result = compose_html("Тело", "Alice", None)
    assert result == "Тело\n\n— Alice"


def test_compose_html_no_body():
    result = compose_html(None, "Alice", "Другое")
    assert result == "— Alice (<i>Другое</i>)"
