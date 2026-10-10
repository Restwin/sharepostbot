"""Tests for the security helper (safe compare)."""

from __future__ import annotations

from bot.utils.security import safe_equal


def test_safe_equal_constant_time():
    assert safe_equal("abc", "abc") is True
    assert safe_equal("abc", "abd") is False
    assert safe_equal("", "") is True
    assert safe_equal("a", "ab") is False
