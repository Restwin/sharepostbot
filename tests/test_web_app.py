"""Tests for the control/webhook HTTP app: Bearer bypass rules."""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from bot.config import Settings
from bot.web.app import auth_middleware, build_webhook_app


def _settings(*, webhook: bool = False) -> Settings:
    return Settings(
        bot_token="1234567890:TESTTESTTEST",
        bot_name="testbot",
        main_channel_id=-100,
        webhook_url="https://test.local" if webhook else "",
        webhook_secret="secret" if webhook else "",
        webhook_public_url="https://test.local" if webhook else "",
        http_api_password="pw",
    )


async def _call_middleware(path: str, settings: Settings, authorization: str | None = None):
    request = make_mocked_request(
        "POST",
        path,
        app=web.Application(),
        headers={"Authorization": authorization} if authorization else {},
    )
    request.app["settings"] = settings

    async def handler(_request):
        return web.json_response({"ok": True})

    return await auth_middleware(request, handler)


async def test_health_bypasses_auth():
    response = await _call_middleware("/health", _settings())
    assert response.status == 200


async def test_version_requires_bearer():
    response = await _call_middleware("/version", _settings())
    assert response.status == 401


async def test_version_accepts_correct_bearer():
    response = await _call_middleware("/version", _settings(), authorization="Bearer pw")
    assert response.status == 200


async def test_webhook_path_bypasses_bearer_auth():
    settings = _settings(webhook=True)
    # Telegram sends updates without an Authorization header; the middleware
    # must not reject them, the secret token check in the handler does that.
    response = await _call_middleware(settings.webhook_path, settings)
    assert response.status == 200


async def test_webhook_app_registers_control_routes():
    settings = _settings(webhook=True)
    bot = object()  # not used by route registration
    app = build_webhook_app(bot, Dispatcher(storage=MemoryStorage()), settings)
    paths = {route.resource.canonical for route in app.router.routes()}
    assert settings.webhook_path in paths
    assert "/health" in paths
    assert "/ready" in paths
    assert "/version" in paths
