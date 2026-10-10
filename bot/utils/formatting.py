"""HTML formatting helpers for post signatures.

Output is always ParseMode.HTML. Telegram HTML rules:
- escape & < > with &amp; &lt; &gt;
- allowed tags: b, i, u, s, code, pre, a, blockquote, spoiler, tg-spoiler
"""

from __future__ import annotations

import re
from html import escape, unescape


def html_escape(text: str | None) -> str:
    return escape(text or "", quote=False)


_TAG_RE = re.compile(r"<[^>]*>")


def strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities → plain text."""
    return unescape(_TAG_RE.sub("", text or "")).strip()


def make_preview(html: str | None, limit: int = 80) -> str:
    """Plain-text preview of an HTML body, truncated to `limit` chars."""
    return strip_html(html or "")[:limit]
