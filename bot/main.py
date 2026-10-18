"""Wiring: build dispatcher + bot, register routers and middlewares,
run webhook or polling depending on settings.
"""

from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.chat_action import ChatActionMiddleware
from aiohttp import web
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import __version__
from bot.config import Settings
from bot.db.init_db import init_db
from bot.db.session import create_engine, create_session_factory
from bot.handlers import access as access_handlers
from bot.handlers import (
    add_chat,
    admin,
    chat_manage,
    common,
    errors,
    links,
    onboarding,
    posts,
    repost,
    wizard,
)
from bot.handlers import admin_users as admin_users_handlers
from bot.logging_setup import configure_logging, get_logger
from bot.middlewares.access import install_access_gates
from bot.middlewares.guest_gate import GuestGateMiddleware
from bot.middlewares.logging import LoggingMiddleware
from bot.middlewares.media_group import MediaGroupCacheMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware
from bot.services.access import AccessService
from bot.services.media_group_cache import MediaGroupCache
from bot.services.tech_chat import TechChatSink
from bot.session import RetryingAiohttpSession
from bot.web.app import build_control_app, build_webhook_app


async def _on_startup(
    bot: Bot,
    settings: Settings,
    dispatcher: Dispatcher,
) -> None:
    log = get_logger("bot.startup")
    # aiogram does not inject session_factory into startup; read it from the
    # dispatcher data stored in run_async.
    session_factory: async_sessionmaker[AsyncSession] = dispatcher["session_factory"]

    if settings.is_webhook_mode:
        url = f"{settings.webhook_public_url.rstrip('/')}{settings.webhook_path}"
        try:
            await bot.set_webhook(
                url=url,
                secret_token=settings.webhook_secret,
                allowed_updates=dispatcher.resolve_used_update_types(),
            )
            log.info("webhook_set", url=url)
        except Exception as exc:
            log.error("set_webhook_failed", url=url, error=str(exc))
    else:
        try:
            await bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            log.warning("delete_webhook_failed")
        log.info("polling_mode")

    # Register command menus (split by role) — runs in BOTH modes.
    from bot.commands import register_commands

    try:
        await register_commands(bot, settings, session_factory)
    except Exception as exc:
        log.warning("register_commands_failed", error=str(exc))

    tech_sink: TechChatSink = dispatcher["tech_sink"]
    tech_sink.attach(bot)

    # Warm the main-channel check now: if the bot cannot see the channel, an
    # error is logged and forwarded to the tech chat, and publishing stays
    # gated until the channel is reachable again.
    from bot.services.membership import MembershipService

    membership: MembershipService = dispatcher["membership"]
    await membership.bot_in_main_channel()

    log.info(
        "bot_started",
        version=__version__,
        mode="webhook" if settings.is_webhook_mode else "polling",
        to_tech="system",
    )


async def _on_shutdown(bot: Bot, settings: Settings, dispatcher: Dispatcher) -> None:
    log = get_logger("bot.shutdown")
    log.info("bot_stopping", to_tech="system")
    tech_sink: TechChatSink = dispatcher["tech_sink"]
    await tech_sink.aclose()
    if settings.is_webhook_mode:
        try:
            await bot.delete_webhook()
        except Exception:
            log.warning("delete_webhook_failed")
    await bot.session.close()
    log.info("shutdown_complete")


def build_dispatcher(settings: Settings) -> Dispatcher:
    """Wire routers + middlewares into a Dispatcher."""
    dp = Dispatcher(storage=MemoryStorage())

    errors.register_error_handler(dp)

    # Middlewares (outermost → innermost)
    dp.update.outer_middleware(LoggingMiddleware())
    media_group_cache = MediaGroupCache()
    # must be outer: album items match no handler, so an inner middleware would
    # never run and the cache would stay empty
    dp.message.outer_middleware(MediaGroupCacheMiddleware(media_group_cache))
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
    dp.message.middleware(ChatActionMiddleware())

    # Routers (order matters: more specific first)
    dp.include_router(common.router)
    dp.include_router(access_handlers.router)
    dp.include_router(admin.router)
    dp.include_router(admin_users_handlers.router)
    dp.include_router(posts.router)
    dp.include_router(links.router)
    dp.include_router(chat_manage.router)
    dp.include_router(add_chat.router)
    dp.include_router(wizard.router)
    dp.include_router(onboarding.router)
    dp.include_router(repost.router)

    # Shared services accessible from handlers via data dict
    dp["media_group_cache"] = media_group_cache

    return dp


def build_dispatcher_with_deps(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
) -> Dispatcher:
    """Build dispatcher and wire access-control services that need the DB.

    build_dispatcher stays for tests without access control; run_async installs
    the access/membership gates once the bot instance exists.
    """
    dp = build_dispatcher(settings)
    access = AccessService(settings, session_factory)
    # dp key must match the handler parameter name (`access`): aiogram injects by name
    dp["access"] = access
    return dp


def build_bot(settings: Settings) -> Bot:
    session = RetryingAiohttpSession(
        max_retries=settings.api_max_retries,
        retry_base_delay=settings.api_retry_base_delay,
        timeout=settings.api_timeout_seconds,
    )
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )


async def run_async(settings: Settings) -> None:
    tech_sink = TechChatSink(
        settings.debug_info_chat_ids,
        level=settings.log_chat_level,
        categories=settings.log_chat_events,
    )
    configure_logging(
        settings.log_level,
        settings.log_dir,
        log_json=settings.log_json,
        log_max_bytes=settings.log_max_bytes,
        log_backup_count=settings.log_backup_count,
        secrets=(settings.bot_token, settings.webhook_secret, settings.http_api_password),
        extra_processor=tech_sink.processor,
    )
    log = get_logger("bot.main")

    # Ensure DB dir exists
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(settings)
    await init_db(engine)
    session_factory = create_session_factory(engine)

    bot = build_bot(settings)
    dp = build_dispatcher_with_deps(settings, session_factory)

    # Inject context data accessible from handlers via data dict
    dp["settings"] = settings
    dp["session_factory"] = session_factory
    dp["bot"] = bot
    dp["tech_sink"] = tech_sink

    # Membership + access gates need the bot instance, so install them here.
    from bot.services.membership import MembershipService

    membership = MembershipService(bot, settings)
    dp["membership"] = membership
    access = dp["access"]
    install_access_gates(
        repost.router, wizard.router, access, membership, session_factory, settings
    )
    # Guest gate: hide every command from non-members of the main channel.
    dp.message.middleware(GuestGateMiddleware(access, membership))

    dp.startup.register(_on_startup)
    dp.shutdown.register(_on_shutdown)

    # periodic local DB snapshots (rotating files)
    from bot.services.backup import backup_loop

    backup_task = asyncio.create_task(backup_loop(settings))

    runners: list[web.AppRunner] = []
    try:
        # Always start control API (health/readiness/version) on HTTP_PORT.
        # In webhook mode the webhook server runs on WEBHOOK_PORT separately.
        control_app = build_control_app(bot, settings)
        control_runner = web.AppRunner(control_app)
        await control_runner.setup()
        control_site = web.TCPSite(control_runner, host=settings.http_host, port=settings.http_port)
        await control_site.start()
        runners.append(control_runner)
        log.info("control_api", host=settings.http_host, port=settings.http_port)

        if settings.is_webhook_mode:
            app = build_webhook_app(bot, dp, settings)
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host="0.0.0.0", port=settings.webhook_port)
            await site.start()
            runners.append(runner)
            # In webhook mode we manage startup/shutdown explicitly (no start_polling).
            await dp.emit_startup(bot=bot, settings=settings, dispatcher=dp)
            log.info("listening", port=settings.webhook_port, path=settings.webhook_path)

            # Run forever until SIGTERM/SIGINT — graceful shutdown cleans up.
            stop_event = asyncio.Event()
            _install_signal_handlers(stop_event)
            await stop_event.wait()
            await dp.emit_shutdown(bot=bot, settings=settings, dispatcher=dp)
        else:
            # start_polling emits startup/shutdown itself; calling emit_startup
            # here would fire handlers twice. SIGTERM/SIGINT make a clean stop.
            stop_event = asyncio.Event()
            _install_signal_handlers(stop_event)
            polling_task = asyncio.create_task(
                dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
            )
            # Race: whichever fires first (polling ends OR signal) wins.
            done, _pending = await asyncio.wait(
                {polling_task, asyncio.create_task(stop_event.wait())},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if polling_task not in done:
                polling_task.cancel()
                try:
                    await polling_task
                except (asyncio.CancelledError, Exception):  # noqa: S110 — shutdown path
                    pass
    finally:
        # Stop the periodic backup task before tearing down the engine.
        backup_task.cancel()
        try:
            await backup_task
        except (asyncio.CancelledError, Exception):  # noqa: S110 — shutdown path
            pass
        # Graceful cleanup of HTTP runners (closes keepalive connections cleanly).
        for runner in runners:
            try:
                await runner.cleanup()
            except Exception:
                log.warning("runner_cleanup_failed")
        await engine.dispose()


def run() -> None:
    from bot.config import load_settings

    settings = load_settings()
    try:
        asyncio.run(run_async(settings))
    except KeyboardInterrupt:
        pass


def _install_signal_handlers(stop_event: asyncio.Event) -> None:
    """Set the stop event on SIGTERM/SIGINT for a graceful exit.

    Windows lacks SIGTERM handlers; asyncio.run() also turns Ctrl-C into
    KeyboardInterrupt, caught in `run()`.
    """
    import signal

    loop = asyncio.get_running_loop()

    def _stop(*_args: object) -> None:
        if not stop_event.is_set():
            stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except (NotImplementedError, RuntimeError):
            # Not supported on this platform (Windows) — fall back to KeyboardInterrupt.
            pass


if __name__ == "__main__":
    run()
