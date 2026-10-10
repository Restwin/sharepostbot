"""Security helpers: constant-time compare of the control-API password."""

from __future__ import annotations

import hmac


def safe_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
