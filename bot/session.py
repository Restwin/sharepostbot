"""AiohttpSession subclass with automatic retry on transient network errors.

The default AiohttpSession raises TelegramNetworkError on the first failed call
to api.telegram.org (DNS hiccup, transient TCP failure, momentary packet loss),
which makes every handler call a potential crash on unstable connections. This
session retries the underlying HTTP request with exponential backoff before
giving up.

Configuration (via Settings):
  API_TIMEOUT_SECONDS: total per-request timeout (default 30)
  API_MAX_RETRIES: retries on TelegramNetworkError (default 3)
  API_RETRY_BASE_DELAY: initial backoff delay in seconds (default 0.5)
"""

from __future__ import annotations

import asyncio
import random
from typing import Any

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramServerError
from aiogram.methods.base import TelegramType

from bot.logging_setup import get_logger

_log = get_logger("bot.session")


class RetryingAiohttpSession(AiohttpSession):
    """AiohttpSession that retries on transient errors with backoff.

    Retries on:
    - TelegramNetworkError: connection failures (DNS, TCP, timeout, ServerDisconnected)
    - TelegramServerError: 5xx responses from Telegram (500, 502, 503, transient)
    - TelegramRetryAfter: 429 rate limit. Sleeps `retry_after` seconds (respects
      Telegram's hint) before retrying instead of hammering and getting worse.
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        retry_base_delay: float = 0.5,
        timeout: float = 30.0,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, **kwargs)
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay

    async def make_request(
        self,
        bot: Bot,
        method: Any,
        timeout: int | None = None,  # noqa: ASYNC109 — aiogram API signature
    ) -> TelegramType:
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return await super().make_request(bot, method, timeout=timeout)
            except TelegramRetryAfter as exc:
                # honor Telegram's retry_after hint (plus a little jitter)
                # instead of our own backoff
                last_exc = exc
                if attempt >= self._max_retries:
                    break
                delay = float(exc.retry_after) + random.uniform(0, 0.25)
                _log.warning(
                    "api_rate_limited",
                    method=method.__api_method__,
                    attempt=attempt + 1,
                    retry_after=exc.retry_after,
                    sleep=round(delay, 2),
                )
                await asyncio.sleep(delay)
            except (TelegramNetworkError, TelegramServerError) as exc:
                last_exc = exc
                if attempt >= self._max_retries:
                    break
                # exponential backoff with jitter: 0.5s, 1s, 2s, 4s, ... + 0-250ms
                delay = self._retry_base_delay * (2**attempt) + random.uniform(0, 0.25)
                _log.warning(
                    "api_retry",
                    method=method.__api_method__,
                    attempt=attempt + 1,
                    max_retries=self._max_retries,
                    delay=round(delay, 2),
                    error=str(exc),
                )
                await asyncio.sleep(delay)
        # All retries exhausted
        assert last_exc is not None
        _log.error(
            "api_retry_exhausted",
            method=method.__api_method__,
            max_retries=self._max_retries,
            error=str(last_exc),
        )
        raise last_exc
