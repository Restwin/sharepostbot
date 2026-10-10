"""Build the signature appended to posts.

Signature format (single line):

    — {author} из {chat} ({category} · пост)

- `{author}` — the author mention.
- `{chat}` — the source chat name, linked to the invite link (so a channel
  subscriber can join), or `«chat»` in quotes when no link is available.
- `{category}` — the post category (italic).
- `пост` — a link to the source message itself (t.me/c/…), present only for
  supergroups/channels (basic groups have no per-message link).

For wizard posts (from PM) the line is:

    — {author} ({category} · из ЛС)

Body HTML comes from aiogram's built-in renderers (`Message.html_text` and
`HtmlDecoration.unparse` for captions) — never hand-roll entity wrapping.

The signature is built with `aiogram.utils.formatting` (Text / TextMention /
TextLink): correct HTML escaping for free and support for all entity types,
including blockquote and custom_emoji.
"""

from __future__ import annotations

from dataclasses import dataclass

from aiogram.enums import ChatType
from aiogram.types import Chat, Message, User
from aiogram.utils.formatting import Italic, Text, TextLink, TextMention
from aiogram.utils.text_decorations import HtmlDecoration

from bot import texts
from bot.db.models import SavedChat
from bot.utils.telegram_links import post_link, public_chat_link

# Telegram message-length limits.
MESSAGE_LIMIT = 4096
CAPTION_LIMIT = 1024


def caption_over_limit(caption: str, is_text: bool) -> int | None:
    """Return the applicable limit if `caption` exceeds it, else None."""
    limit = MESSAGE_LIMIT if is_text else CAPTION_LIMIT
    return limit if len(caption) > limit else None


@dataclass(frozen=True, slots=True)
class PostSignature:
    """The signature block to append below the post body.

    `text` is a ready-to-send HTML string (parse_mode=HTML).
    """

    text: str


def author_display_name(user: User) -> str:
    name = (user.first_name or user.username or f"id:{user.id}").strip()
    if user.last_name:
        name = f"{name} {user.last_name.strip()}"
    return name


def render_message_body(message: Message) -> str:
    """Render a message's text or caption as HTML, preserving all entities.

    Uses aiogram's built-in renderers:
    - `message.html_text` for text messages
    - `HtmlDecoration().unparse(caption, caption_entities)` for media captions
    """
    if message.text is not None:
        return message.html_text
    if message.caption is not None:
        return HtmlDecoration().unparse(
            text=message.caption,
            entities=message.caption_entities or [],
        )
    return ""


def build_signature(
    *,
    author: User,
    source_chat: Chat | None,
    saved_chat: SavedChat | None,
    message_id_in_source: int | None,
) -> PostSignature:
    """Build the signature body (author + source), without the category.

    The category and the leading "— " are added later by `compose_html`.
    """
    nodes: list[Text] = [TextMention(author_display_name(author), user=author)]

    if source_chat is not None and source_chat.type != ChatType.PRIVATE:
        chat_link_text, chat_link_url = _resolve_source_chat(source_chat, saved_chat)
        if chat_link_url is not None:
            nodes.append(
                Text(texts.POST_SIG_FROM_LINK, TextLink(chat_link_text, url=chat_link_url))
            )
        else:
            nodes.append(Text(texts.POST_SIG_FROM_QUOTED.format(name=chat_link_text)))

        # Direct link to the source message ("пост"), only for supergroups/channels.
        if message_id_in_source is not None and str(source_chat.id).startswith("-100"):
            nodes.append(
                Text(
                    " · ",
                    TextLink(
                        texts.POST_SIG_POST_LINK,
                        url=post_link(source_chat.id, message_id_in_source),
                    ),
                )
            )
    elif source_chat is not None and source_chat.type == ChatType.PRIVATE:
        # PM post: no source chat/message, so the "пост" slot shows "из ЛС".
        nodes.append(Text(texts.POST_SIG_PM_SUFFIX))

    return PostSignature(text=_render_text_to_html(Text(*nodes)))


def _render_text_to_html(node: Text) -> str:
    """Render a formatting.Text node to an HTML string.

    Uses aiogram's HtmlDecoration under the hood (the same one used by
    `message.html_text`), so escaping and entity wrapping match exactly.
    """
    kwargs = node.as_kwargs()
    raw_text: str = kwargs["text"]
    entities = kwargs.get("entities") or []
    return HtmlDecoration().unparse(text=raw_text, entities=entities)


def compose_html(body_html: str | None, signature_text: str, category: str | None) -> str:
    """Compose a caption: body, then a single signature line.

    The signature line is `— {author} из {chat} ({category} · пост)`. The
    category and the source are omitted when absent.
    """
    parts: list[str] = []
    if body_html:
        parts.append(body_html)

    line = signature_text
    if category:
        cat = category_line(category)
        if " · " in line:
            # "{author} из {chat} · {пост}" → "{author} из {chat} ({category} · {пост})"
            head, post = line.rsplit(" · ", 1)
            line = f"{head} ({cat} · {post})"
        else:
            # PM or basic group: "{author}" / "{author} из {chat}"
            line = f"{line} ({cat})"

    parts.append(f"— {line}")
    return "\n\n".join(parts)


def category_line(category: str) -> str:
    """Render the category as italic text for the signature line."""
    return _render_text_to_html(Italic(category))


def _resolve_source_chat(source_chat: Chat, saved_chat: SavedChat | None) -> tuple[str, str | None]:
    """Return (display_name, link_url_or_None) for the source chat.

    Link precedence: public @username → saved invite link → no link (bare title).
    """
    if source_chat.username:
        name = saved_chat.exact_name if saved_chat else (source_chat.title or source_chat.username)
        return name, public_chat_link(source_chat.username)

    if saved_chat and saved_chat.join_link:
        return saved_chat.exact_name, saved_chat.join_link

    return source_chat.title or texts.POST_SIG_NO_CHAT_TITLE, None


__all__ = [
    "PostSignature",
    "author_display_name",
    "build_signature",
    "category_line",
    "compose_html",
    "render_message_body",
]
