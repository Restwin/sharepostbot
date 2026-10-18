"""Telegram URL helpers for chat / post / invite links."""

from __future__ import annotations

import re


def post_link(chat_id: int, message_id: int) -> str:
    """Link to a message in a private supergroup/channel.

    chat_id is expected to be -100xxxxxxxxxx (supergroup/channel).
    Strips the -100 prefix to form the t.me/c/<id>/<msg> URL.
    """
    s = str(chat_id)
    if s.startswith("-100"):
        body = s[4:]
    elif s.startswith("-"):
        body = s[1:]
    else:
        body = s
    return f"https://t.me/c/{body}/{message_id}"


def public_chat_link(username: str) -> str:
    return f"https://t.me/{username.lstrip('@')}"


def is_valid_invite_link(link: str) -> bool:
    return link.startswith(("https://t.me/joinchat/", "https://t.me/+"))


_USERNAME_RE = re.compile(r"[A-Za-z0-9_]{5,32}\Z")
_INVITE_HASH_RE = re.compile(r"[A-Za-z0-9_-]{8,}\Z")


def parse_chat_link(raw: str) -> tuple[str, str] | None:
    """Parse a Telegram chat link into (kind, target).

    kind = "username" → public chat (resolvable via bot.get_chat("@target")).
    kind = "invite"    → private invite link (not resolvable via Bot API).

    Accepted forms: @username, t.me/username, https://t.me/username,
    https://t.me/+hash, https://t.me/joinchat/hash.

    Anything with a query string (t.me/proxy?…, t.me/socks?…,
    t.me/share/url?…) is rejected, as are malformed usernames and hashes.

    Returns None if the input is not a recognizable chat link.
    """
    link = raw.strip().rstrip("/")
    if not link:
        return None
    # query strings and fragments turn a chat link into an action link
    # (proxy/socks/share); reject them outright
    if any(c in link for c in ("?", "#", "&", " ")):
        return None
    if link.startswith("@"):
        username = link[1:].split("/")[0]
        return ("username", username) if _USERNAME_RE.fullmatch(username) else None
    for scheme in ("https://", "http://"):
        if link.lower().startswith(scheme):
            link = link[len(scheme) :]
            break
    if not link.lower().startswith("t.me/"):
        return None
    link = link[5:]
    if not link:
        return None
    if link.lower().startswith("joinchat/"):
        target = link[len("joinchat/") :]
        return ("invite", target) if _INVITE_HASH_RE.fullmatch(target) else None
    if link.startswith("+"):
        target = link[1:]
        return ("invite", link) if _INVITE_HASH_RE.fullmatch(target) else None
    username = link.split("/")[0]
    return ("username", username) if _USERNAME_RE.fullmatch(username) else None
