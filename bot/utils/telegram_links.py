"""Telegram URL helpers for chat / post / invite links."""

from __future__ import annotations


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


def parse_chat_link(raw: str) -> tuple[str, str] | None:
    """Parse a Telegram chat link into (kind, target).

    kind = "username" → public chat (resolvable via bot.get_chat("@target")).
    kind = "invite"    → private invite link (not resolvable via Bot API).

    Accepted forms: @username, t.me/username, https://t.me/username,
    https://t.me/+hash, https://t.me/joinchat/hash.

    Returns None if the input is not a recognizable chat link.
    """
    link = raw.strip().rstrip("/")
    if not link:
        return None
    if link.startswith("@"):
        username = link[1:].split("/")[0]
        return ("username", username) if username else None
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
        return ("invite", link[len("joinchat/") :])
    if link.startswith("+"):
        return ("invite", link)
    username = link.split("/")[0]
    return ("username", username) if username else None
