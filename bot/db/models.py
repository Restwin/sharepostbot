"""SQLAlchemy models.

SavedChat is keyed by the immutable `chat_id`; AppUser carries the role-based
access model (staff / allow / blocked) with a free-form block reason.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import IntEnum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class IntEnumType(TypeDecorator[int]):
    """Store an IntEnum as INTEGER while returning the enum member on read.

    Without this, SQLAlchemy returns a plain `int`, and code calling `.name`
    on the value crashes. Storage stays INTEGER, so no data migration needed.
    """

    impl = Integer
    cache_ok = True

    def __init__(self, enum_cls: type[IntEnum]) -> None:
        self._enum_cls = enum_cls
        super().__init__()

    def process_bind_param(self, value: IntEnum | int | None, dialect: object) -> int | None:
        if value is None:
            return None
        return int(value)

    def process_result_value(self, value: int | None, dialect: object) -> IntEnum | None:
        if value is None:
            return None
        return self._enum_cls(int(value))


class UserRole(IntEnum):
    """Access tier for a user.

    UNKNOWN  — default for freshly seen users. NOT a block: a regular user
               whose ability to publish is governed by channel membership
               (enforced separately). Being added to the community channel is
               enough to publish.
    ALLOW    — explicit positive marker. Functionally the same as UNKNOWN for
               publishing; kept so admins can mark a user as vetted if desired.
    BLOCKED  — may not publish; `block_reason` and `restrict_mode` explain why
               and where. Can still use /whyblocked and /contacts in PM.
    STAFF    — administrator: may manage chats, contacts, users, settings, and
               bypasses the channel-membership gate.
    """

    UNKNOWN = 0
    ALLOW = 1
    BLOCKED = 2
    STAFF = 3


class RestrictMode(IntEnum):
    """Where a BLOCKED user is blocked from publishing.

    PM_ONLY      — only PM wizard is blocked; mention in chat still works.
    MENTION_ONLY — only mention-in-chat is blocked; PM wizard still works.
    BOTH         — blocked everywhere (default for BLOCKED).
    """

    PM_ONLY = 0
    MENTION_ONLY = 1
    BOTH = 2


class SavedChat(Base):
    __tablename__ = "SavedChats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    exact_name: Mapped[str] = mapped_column(String, nullable=False)
    join_link: Mapped[str] = mapped_column(String, nullable=False)
    # Where the invite link came from: "bot" (exported by the bot on onboarding,
    # revoked if the bot loses admin) or "pm" (a permanent link provided by the
    # user via /add_chat — survives losing admin rights).
    link_source: Mapped[str] = mapped_column(String(8), nullable=False, default="bot")
    # Type of the stored link: "open" — no approval required; "confirm" — new
    # members must be approved by admins (join requests); "" — no link.
    join_approval: Mapped[str] = mapped_column(String(8), nullable=False, default="open")
    # Telegram user id of whoever registered this chat (via /add_chat or
    # onboarding). Used to show each user only their own chats.
    added_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Blacklist flag: when True, reposting (reply+mention) from this chat is
    # denied before category selection. Set via /block_chat, cleared via
    # /unblock_chat.
    is_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Free-form reason shown when reposting from a blocked chat is denied.
    block_reason: Mapped[str] = mapped_column(String, nullable=False, default="")
    # Telegram user id of the STAFF admin who blocked this chat (None otherwise).
    blocked_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (Index("ix_savedchats_exact_name", "exact_name"),)


class AppUser(Base):
    __tablename__ = "Users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    joined: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
    )
    # Last interaction with the bot (any update). Drives the "users" list
    # ordering (most recent first; NULL rows sort last).
    last_activity: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # --- Role-based access model ---
    role: Mapped[UserRole] = mapped_column(
        IntEnumType(UserRole), default=UserRole.UNKNOWN, nullable=False
    )
    block_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    restrict_mode: Mapped[RestrictMode] = mapped_column(
        IntEnumType(RestrictMode), default=RestrictMode.BOTH, nullable=False
    )
    # Telegram user id of the STAFF admin who blocked this user (None otherwise).
    # Shown to the blocked user via /whyblocked.
    blocked_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    __table_args__ = (
        Index("ix_users_username", "username"),
        Index("ix_users_role", "role"),
    )


class AdminContact(Base):
    """Admin-facing contact card shown via /contacts.

    One row per admin. `user_id` references AppUser.id (a STAFF user).
    `public_role` is a free-form label shown to users ("owner", "moderator",
    "tech admin", …). `comment` is an optional free-form note.
    `display_order` controls listing order (smaller = higher).
    """

    __tablename__ = "AdminContacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True)
    public_role: Mapped[str] = mapped_column(String(64), nullable=False, default="admin")
    comment: Mapped[str] = mapped_column(String, nullable=False, default="")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)


class PostCategory(Base):
    """Post category shown as a header line on published posts.

    Admin-editable via /categories. Posts store only the category name as a
    snapshot at publish time (no FK), so removing/renaming a category never
    breaks historical posts.
    """

    __tablename__ = "PostCategories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PublishedPost(Base):
    """Statistics record for every published post.

    One row per successful publish. `author_*` is the publisher (the user who
    triggered the publish — the wizard user in PM, or the reply+mention requester
    in a source chat). `source` is "pm" or "mention"; `source_chat_*` is filled
    only for mentions. `category` and `preview` are snapshots (no FK).
    """

    __tablename__ = "PublishedPosts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    author_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    author_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    source: Mapped[str] = mapped_column(String(16), nullable=False, default="pm")
    source_chat_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_chat_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    category: Mapped[str] = mapped_column(String, nullable=False, default="")
    preview: Mapped[str] = mapped_column(String, nullable=False, default="")
    # Comma-separated message ids of the post in the main channel (1 id for a
    # single message, N for an album). Empty when ids were not tracked.
    # Enables edit/delete: the bot needs these ids to edit/delete its post.
    channel_message_ids: Mapped[str] = mapped_column(String, nullable=False, default="")
    # Soft-delete flag set when the post is removed from the channel via the
    # edit/delete flow; such posts are excluded from stats and listings.
    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # --- Edit ("обновить") support ---
    # The id of the original source message (the PM content message, or the
    # replied-to message in a source chat). Lets the bot track edits to the
    # source via the `edited_message` handler.
    source_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Snapshot of the source content, refreshed by the `edited_message` handler:
    # kind in text/photo/video/document/album/poll, full HTML body, and the media
    # file_id (for single photo/video/document). Used to update the post text or
    # caption (with signature) when editing an edited source.
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="text")
    body_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    file_id: Mapped[str] = mapped_column(String, nullable=False, default="")
    sig_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # True once the source message has been edited after publish (set by the
    # `edited_message` handler). Gates the "edit" action.
    source_edited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # True when the source edit changed the media file itself (single
    # photo/video/document). Drives editMessageMedia vs editMessageCaption.
    source_media_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
    )

    __table_args__ = (Index("ix_publishedposts_published_at", "published_at"),)


class CommunityLinks(Base):
    """Single-row table of community links shown in the inline menu.

    Edited by admins via `/links` and the "Ссылки" menu. The bottom of the main
    menu renders these as URL buttons ("Правила публикации постов", "Канал",
    "Основной чат"); when a value is empty the button falls back to a
    "ссылка не заполнена" placeholder.
    """

    __tablename__ = "CommunityLinks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    rules_url: Mapped[str | None] = mapped_column(String, nullable=True)
    channel_url: Mapped[str | None] = mapped_column(String, nullable=True)
    main_chat_url: Mapped[str | None] = mapped_column(String, nullable=True)
