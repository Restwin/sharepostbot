"""Post management: /myposts, /posts, and the edit/delete inline actions.

Let a post author (or a STAFF admin) edit or remove a post from the main
channel. The bot can only act on a channel post if it stored that post's message
ids at publish time (`PublishedPost.channel_message_ids`).

- `/myposts`: the user's own recent posts with edit/delete buttons.
- `/posts [N]`: STAFF-only; recent posts from anyone.
- edit: update the channel message in place (preserving comments and reactions)
  with the edited source text + signature; rejected when the source was not
  edited.
- delete: remove the post from the channel (marks it deleted in the DB).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandObject
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaDocument,
    InputMediaPhoto,
    InputMediaVideo,
    LinkPreviewOptions,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import texts
from bot.config import Settings
from bot.db.models import PublishedPost
from bot.db.repo.stats import PostStatRepository
from bot.logging_setup import get_logger
from bot.services.access import AccessService, PublishChannel
from bot.services.content_types import classify_content, extract_file_id
from bot.services.post_builder import compose_html, render_message_body
from bot.utils.callbacks import MenuCallback, PostManageCallback
from bot.utils.formatting import html_escape
from bot.utils.replies import safe_answer, temp_reply
from bot.utils.telegram_links import post_link

router = Router(name="posts")
_log = get_logger("bot.posts")

_DELETE_WINDOW = timedelta(hours=48)
_DEFAULT_LIMIT = 5
_MAX_LIMIT = 10
_ADMIN_POSTS_LIMIT = 8
_PREVIEW_LIMIT = 60

# Content kinds the edit action can update in place from the stored snapshot.
_EDITABLE_KINDS = ("text", "photo", "video", "document")

_INSTRUCTIONS = texts.POSTS_INSTRUCTIONS


def _parse_ids(raw: str) -> list[int]:
    ids: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            ids.append(int(part))
    return ids


def _within_window(published_at: datetime | None) -> bool:
    if published_at is None:
        return False
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - published_at <= _DELETE_WINDOW


async def _is_staff(user_id: int, access: AccessService) -> bool:
    decision = await access.resolve(
        user_id,
        channel=PublishChannel.PM,
    )
    return decision.is_staff


def _post_url(post: PublishedPost, main_channel_id: int) -> str | None:
    ids = _parse_ids(post.channel_message_ids)
    if not ids:
        return None
    return post_link(main_channel_id, ids[0])


def _post_line(post: PublishedPost, idx: int, main_channel_id: int) -> str:
    when = post.published_at.strftime("%d.%m %H:%M") if post.published_at else ""
    category = html_escape(post.category or texts.STATS_CATEGORY_NONE)
    raw_preview = (post.preview or "—").strip()
    if len(raw_preview) > _PREVIEW_LIMIT:
        preview = html_escape(raw_preview[:_PREVIEW_LIMIT]) + "…"
    else:
        preview = html_escape(raw_preview)
    link = _post_url(post, main_channel_id)
    if link:
        preview = f'<a href="{link}">{preview}</a>'
    return f"<b>{idx}.</b> {preview}\n<i>{category}</i> · <i>{when}</i>"


def _manage_keyboard(
    posts: list[PublishedPost], *, with_myposts_button: bool = False
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i, post in enumerate(posts, 1):
        edit_label = texts.POST_BTN_EDIT_ALBUM if post.kind == "album" else texts.POST_BTN_EDIT
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{edit_label} {i}",
                    callback_data=PostManageCallback(action="edit", post_id=post.id).pack(),
                ),
                InlineKeyboardButton(
                    text=f"{texts.POST_BTN_DELETE} {i}",
                    callback_data=PostManageCallback(action="delete", post_id=post.id).pack(),
                ),
            ]
        )
    bottom = [
        InlineKeyboardButton(
            text=texts.MENU_BTN_BACK,
            callback_data=MenuCallback(action="back").pack(),
        )
    ]
    if with_myposts_button:
        bottom.append(
            InlineKeyboardButton(
                text=texts.MENU_BTN_MY_POSTS,
                callback_data=MenuCallback(action="myposts").pack(),
            )
        )
    rows.append(bottom)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_posts(
    message: Message,
    posts: list[PublishedPost],
    *,
    title: str,
    empty_text: str,
    main_channel_id: int,
    with_myposts_button: bool = False,
) -> None:
    if not posts:
        await message.answer(empty_text)
        return
    blocks = [title, _INSTRUCTIONS]
    blocks += [_post_line(post, i, main_channel_id) for i, post in enumerate(posts, 1)]
    await message.answer(
        "\n\n".join(blocks),
        reply_markup=_manage_keyboard(posts, with_myposts_button=with_myposts_button),
    )


async def render_recent_posts(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    main_channel_id: int,
    *,
    limit: int = _ADMIN_POSTS_LIMIT,
    with_myposts_button: bool = False,
) -> None:
    """Recent posts from anyone; backs the admin menu button."""
    async with session_factory() as session:
        repo = PostStatRepository(session)
        posts = await repo.get_recent(limit)
    await _render_posts(
        message,
        posts,
        title=texts.RECENT_POSTS_TITLE.format(limit=limit),
        empty_text=texts.RECENT_POSTS_EMPTY,
        main_channel_id=main_channel_id,
        with_myposts_button=with_myposts_button,
    )


async def render_user_posts(
    message: Message,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: int,
    main_channel_id: int,
) -> None:
    """Shared by the /myposts command and the inline menu button."""
    async with session_factory() as session:
        repo = PostStatRepository(session)
        posts = await repo.get_by_author(user_id, _DEFAULT_LIMIT)
    await _render_posts(
        message,
        posts,
        title=texts.MY_POSTS_TITLE,
        empty_text=texts.MY_POSTS_EMPTY,
        main_channel_id=main_channel_id,
    )


@router.message(Command("myposts"), F.chat.type == ChatType.PRIVATE)
async def cmd_myposts(
    message: Message,
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = message.from_user
    if user is None:
        return
    await render_user_posts(message, session_factory, user.id, settings.main_channel_id)


@router.message(Command("posts"), F.chat.type == ChatType.PRIVATE)
async def cmd_posts(
    message: Message,
    command: CommandObject,
    settings: Settings,
    access: AccessService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    user = message.from_user
    if user is None:
        return
    if not await _is_staff(user.id, access):
        await temp_reply(message, texts.POSTS_STAFF_ONLY)
        return

    arg = (command.args or "").strip()
    limit = _DEFAULT_LIMIT
    if arg.isdigit():
        limit = max(1, min(int(arg), _MAX_LIMIT))

    await render_recent_posts(message, session_factory, settings.main_channel_id, limit=limit)


@router.edited_message()
async def on_edited_message(
    edited: Message,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Track edits to source messages so the edit action can detect changes."""
    kind = classify_content(edited)
    if kind not in _EDITABLE_KINDS:
        return
    body_html = render_message_body(edited)
    file_id = extract_file_id(edited)
    async with session_factory() as session:
        repo = PostStatRepository(session)
        posts = await repo.get_by_source(edited.chat.id, edited.message_id)
        if not posts:
            return
        for post in posts:
            if post.kind == "album":
                # Albums are edited text-only: refresh the body snapshot, never
                # the media file, and keep the "album" kind.
                repo.update_source_content(post, body_html=body_html)
            else:
                media_changed = bool(file_id) and file_id != post.file_id
                repo.update_source_content(
                    post, body_html=body_html, file_id=file_id, media_changed=media_changed
                )
        await session.commit()
    _log.info(
        "source_edited",
        chat_id=edited.chat.id,
        message_id=edited.message_id,
        posts=len(posts),
    )


@router.callback_query(PostManageCallback.filter())
async def post_manage_callback(
    query: CallbackQuery,
    callback_data: PostManageCallback,
    bot: Bot,
    settings: Settings,
    access: AccessService,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    if query.from_user is None:
        await safe_answer(query)
        return

    async with session_factory() as session:
        repo = PostStatRepository(session)
        post = await repo.get_by_id(callback_data.post_id)
        if post is None or post.is_deleted:
            await _reply(query, texts.POST_NOT_FOUND)
            return

        # Authorization: the post author or STAFF.
        is_staff = await _is_staff(query.from_user.id, access)
        if not is_staff and post.author_id != query.from_user.id:
            await _reply(query, texts.POST_NOT_AUTHOR)
            return

        if not post.channel_message_ids:
            await _reply(query, texts.POST_NOT_TRACKED)
            return

        message_ids = _parse_ids(post.channel_message_ids)
        if not message_ids:
            await _reply(query, texts.POST_NOT_TRACKED)
            return
        main = settings.main_channel_id

        if callback_data.action == "delete":
            if not _within_window(post.published_at):
                await _reply(query, texts.POST_TOO_OLD)
                return
            await _delete_messages(bot, main, message_ids)
            repo.mark_deleted(post)
            await session.commit()
            await _reply(query, texts.POST_DELETED)
            _log.info("post_deleted", post_id=post.id, by=query.from_user.id)
            return

        if callback_data.action == "edit":
            ok = await _edit(bot, settings, post, query, message_ids[0])
            if ok is None:
                return  # already answered the user
            repo.clear_source_edited(post)
            await session.commit()
            await _reply(query, ok)
            _log.info("post_edited", post_id=post.id, by=query.from_user.id)
            return

    await _reply(query, texts.POST_UNKNOWN_ACTION)


async def _edit(
    bot: Bot,
    settings: Settings,
    post: PublishedPost,
    query: CallbackQuery,
    message_id: int,
) -> str | None:
    """Edit the channel post in place with the edited source text + signature.

    Text → editMessageText. Single media (photo/video/document) → replace the
    media via editMessageMedia when the file changed, otherwise edit only the
    caption. Albums → text/caption only (media is never replaced). All paths
    keep the message id, so comments and reactions are preserved.

    Returns a success message, or None (already answered the user) on rejection.
    """
    if post.source_message_id is None or post.source_chat_id is None:
        await _reply(query, texts.POST_NOT_TRACKED)
        return None
    if not post.source_edited:
        await _reply(query, texts.POST_EDIT_NOT_CHANGED)
        return None
    if post.kind not in _EDITABLE_KINDS and post.kind != "album":
        await _reply(query, texts.POST_EDIT_UNSUPPORTED)
        return None

    # Detect a content-type change (text ↔ media). The stored `kind` no longer
    # matches the source, so an in-place edit would silently drop content.
    _media_kinds = ("photo", "video", "document")
    if post.kind == "text" and post.file_id:
        await _reply(query, texts.POST_EDIT_KIND_CHANGED)
        return None
    if post.kind in _media_kinds and not post.file_id:
        await _reply(query, texts.POST_EDIT_KIND_CHANGED)
        return None

    caption = compose_html(post.body_html or None, post.sig_text, post.category or None)
    main = settings.main_channel_id
    is_album = post.kind == "album"

    try:
        if post.kind == "text":
            await bot.edit_message_text(
                chat_id=main,
                message_id=message_id,
                text=caption,
                parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        elif is_album:
            await bot.edit_message_caption(
                chat_id=main,
                message_id=message_id,
                caption=caption,
                parse_mode="HTML",
            )
        elif post.source_media_changed:
            await bot.edit_message_media(
                chat_id=main,
                message_id=message_id,
                media=_input_media(post.kind, post.file_id, caption),
            )
        else:
            await bot.edit_message_caption(
                chat_id=main,
                message_id=message_id,
                caption=caption,
                parse_mode="HTML",
            )
    except TelegramAPIError as exc:
        _log.warning("post_edit_failed", post_id=post.id, error=str(exc))
        await _reply(query, texts.POST_EDIT_FAILED)
        return None

    if is_album:
        return texts.POST_EDITED_ALBUM
    return texts.POST_EDITED


def _input_media(
    kind: str, file_id: str, caption: str
) -> InputMediaPhoto | InputMediaVideo | InputMediaDocument:
    if kind == "photo":
        return InputMediaPhoto(media=file_id, caption=caption, parse_mode="HTML")
    if kind == "video":
        return InputMediaVideo(media=file_id, caption=caption, parse_mode="HTML")
    return InputMediaDocument(media=file_id, caption=caption, parse_mode="HTML")


async def _delete_messages(bot: Bot, chat_id: int, message_ids: list[int]) -> None:
    for mid in message_ids:
        try:
            await bot.delete_message(chat_id, mid)
        except TelegramAPIError:
            pass  # already deleted or too old, not fatal


async def _announce(query: CallbackQuery, text: str) -> None:
    """Send the result as a chat message (persistent, like the publish flow)."""
    if query.message is not None:
        await query.message.answer(text)


async def _reply(query: CallbackQuery, text: str) -> None:
    """Answer the callback and send `text` as a message reply (not a popup)."""
    await safe_answer(query)
    await _announce(query, text)
