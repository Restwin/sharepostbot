"""Runtime version — single source of truth for /version and the control API.

`bot/__init__.__version__` is authoritative at runtime (works even without
installed package metadata). Keep it in sync with `pyproject.toml` `version`
(used for packaging/publishing).
"""

from __future__ import annotations

from bot import __version__


def get_version() -> str:
    return __version__
