"""aiohttp web app: webhook endpoint, /health, /ready, /version.

Security: /health is open (Docker HEALTHCHECK); /ready and /version require
`Authorization: Bearer <HTTP_API_PASSWORD>` when the password is set. The
webhook endpoint authenticates via the Telegram secret token (aiogram).
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web

from bot.config import Settings
from bot.utils.security import safe_equal
from bot.version import get_version

# Cache get_me() result for readiness checks (TTL 60s) to avoid hitting
# Telegram API on every probe.
_ready_cache_ts: float = 0.0
_ready_cache_bot: str | None = None
_READY_TTL = 60.0


def _check_auth(request: web.Request, settings: Settings) -> bool:
    """True if request passes Bearer auth (or if auth is disabled in dev)."""
    if not settings.http_api_password:
        return True  # dev mode — no password configured
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return False
    token = header[len("Bearer ") :]
    return safe_equal(token, settings.http_api_password)


@web.middleware
async def auth_middleware(
    request: web.Request,
    handler: Callable[[web.Request], Awaitable[web.StreamResponse]],
) -> web.StreamResponse:
    """Bearer-token gate for /ready and /version.

    /health (liveness probe) and the webhook path bypass Bearer auth: the
    webhook is authenticated separately by the Telegram secret token, and
    Telegram sends no Authorization header.

    Settings come from `request.app["settings"]`, so this works on both the
    control app and the webhook app.
    """
    settings: Settings = request.app["settings"]
    # /health is always open: liveness probe for Docker HEALTHCHECK
    if request.path in ("/health", settings.webhook_path):
        return await handler(request)
    if not _check_auth(request, settings):
        return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)


async def health_handler(_request: web.Request) -> web.Response:
    """Liveness probe. Returns 200 if process is alive."""
    return web.json_response({"status": "ok"})


async def readiness_handler(request: web.Request) -> web.Response:
    """Readiness probe: checks Telegram reachability (cached 60s). Returns a
    generic `not_ready` on failure, never the internal error.
    """
    global _ready_cache_ts, _ready_cache_bot
    bot: Bot = request.app["bot"]
    settings: Settings = request.app["settings"]

    now = time.monotonic()
    if _ready_cache_bot is not None and now - _ready_cache_ts < _READY_TTL:
        return web.json_response(
            {"status": "ready", "bot": _ready_cache_bot, "webhook_mode": settings.is_webhook_mode}
        )

    try:
        me = await bot.get_me()
        _ready_cache_bot = me.username
        _ready_cache_ts = now
        return web.json_response(
            {"status": "ready", "bot": me.username, "webhook_mode": settings.is_webhook_mode}
        )
    except Exception:
        # do not echo the exception: it would leak internals
        return web.json_response({"status": "not_ready"}, status=503)


async def version_handler(_request: web.Request) -> web.Response:
    return web.json_response({"version": get_version()})


def build_control_app(bot: Bot, settings: Settings) -> web.Application:
    """Control HTTP app for health/readiness/version on HTTP_PORT (default 8081)."""
    app = web.Application(middlewares=[auth_middleware])
    app["bot"] = bot
    app["settings"] = settings
    app.router.add_get("/health", health_handler)
    app.router.add_get("/ready", readiness_handler)
    app.router.add_get("/version", version_handler)
    return app


def build_webhook_app(bot: Bot, dispatcher: Dispatcher, settings: Settings) -> web.Application:
    """Webhook + control endpoints on a single port (WEBHOOK_PORT).

    The webhook path checks the Telegram secret token; control endpoints follow
    the same Bearer rules as the control app.
    """
    app = web.Application(middlewares=[auth_middleware])
    app["bot"] = bot
    app["settings"] = settings

    webhook_handler = SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=settings.webhook_secret,
    )
    webhook_handler.register(app, path=settings.webhook_path)

    app.router.add_get("/health", health_handler)
    app.router.add_get("/ready", readiness_handler)
    app.router.add_get("/version", version_handler)
    return app
