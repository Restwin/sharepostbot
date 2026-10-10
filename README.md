# sharepostbot

A posting bot for a closed Telegram community. Members reply to a message in a
source chat with a mention of the bot (or run `/post` in PM), pick a category,
and the bot copies the post into the community's main channel with a signature:
author mention, source chat link, category, link to the original post.

sharepostbot is a modern rewrite of [CommunityBot](https://github.com/MrModest/CommunityBot), the legacy C#/.NET bot
that ran this community before. The domain and user experience are the same; the
implementation is new (Python 3, aiogram 3) and free of the old bot's structural
issues: hand-rolled HTML that broke on `<`/`>`, chat lookup by mutable title,
MD5 passwords, .NET 5 EOL.

## Features

**Publishing**

- Repost by reply + mention (`@BotName`) or a configurable trigger phrase
  (`REPOST_TRIGGER_PHRASES`), from any source chat.
- Posts are copied with Telegram's `copy_message`: formatting, links, any
  `<`/`>` characters, custom emoji and media survive intact.
- `/post` wizard in PM: send content, pick a category, confirm.
- Albums are published as albums; polls are forwarded so results stay shared
  with the source chat.
- Every post carries a signature (author mention, source chat, category, link to
  the original message) and is protected from forwarding by default.

**Chats and onboarding**

- Adding the bot to a chat runs onboarding: the chat is registered and an invite
  link for the community can be created (open link, or a link with join-request
  approval).
- `/add_chat <link>` registers a chat manually; `/recheck` refreshes its status.
- Admin tools: `/get_all_chats`, `/block_chat`, `/unblock_chat`, `/whyblocked`,
  `/remove_chat`.

**Access**

- No passwords: roles `UNKNOWN / ALLOW / BLOCKED / STAFF`. Publishing is gated
  by membership in the main channel; staff bypass the gate. Manage roles with
  `/users`, see admins with `/show_admins`.
- Blocked users can check why (`/whyblocked`) and how to reach the admins
  (`/contacts`).

**Posts and stats**

- `/myposts` and `/posts`: list your posts, update them (edit the original
  message first) or delete them.
- `/stats`: posting statistics.

**Operations**

- Long polling by default; set `WEBHOOK_URL` for webhook mode with a verified
  secret token.
- Control HTTP API on `HTTP_PORT`: `/health` (open, used by the Docker
  healthcheck), `/ready` and `/version` (bearer `HTTP_API_PASSWORD`).
- SQLite in WAL mode; `/backup_db` snapshots the database and sends it to the
  debug chats.
- Structured logging (structlog) with secret redaction; bot replies in group
  chats auto-delete after ~1 minute.

## Prerequisites

- A bot token from [@BotFather](https://t.me/BotFather); turn **Group Privacy
  off** in Bot Settings — otherwise the bot won't see plain messages, trigger
  phrases or albums in groups.
- A main channel where the bot can post, and source chats the bot is a member
  of.
- Python 3.12+ for a local run (or Docker), and your Telegram user id for
  `ADMIN_IDS`.

## Quick start (local, long polling)

```bash
# 1. Clone and enter
cd sharepostbot

# 2. Create venv and install
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 3. Configure
cp .env.example .env
# edit .env: BOT_TOKEN, BOT_NAME, MAIN_CHANNEL_ID, ADMIN_IDS, DB_PATH
# leave WEBHOOK_URL empty to use long polling

# 4. Run
python -m bot
```

Bot will start long polling. Open your test bot in Telegram, send `/start`.

## Docker

```bash
cp .env.example .env  # edit
docker compose up -d --build
curl http://127.0.0.1:8081/health
```

## Webhook mode (production)

```bash
# .env:
# WEBHOOK_URL=https://your.public.host
# WEBHOOK_PORT=8080
# WEBHOOK_SECRET=<long random string>
# WEBHOOK_PUBLIC_URL=https://your.public.host

python -m bot
```

Reverse proxy (nginx/Caddy) must terminate HTTPS and forward to `WEBHOOK_PORT`.
Telegram sends updates to `https://your.public.host/webhook` with the
`X-Telegram-Bot-Api-Secret-Token` header, which we verify. The control API
(`/health`, `/ready`, `/version`) always starts on `HTTP_PORT` in both modes.

## Configuration

All settings are environment variables, documented in
[`.env.example`](.env.example). List values (`ADMIN_IDS`, `DEBUG_INFO_CHAT_IDS`,
`REPOST_TRIGGER_PHRASES`) are comma-separated, not JSON. To deploy on a server,
publish the image, put `docker-compose.yml` and a filled `.env` next to it, and
run `docker compose up -d`.

## Posting flow

1. **Reply + mention** in a source chat: reply to a message, mention `@BotName`
   → bot `copy_message`s it to the main channel with a caption signature
   (author mention + source chat link + post link).
2. **Wizard in PM**: `/post` or the menu button → send text/media, pick a
   category, confirm → published to the channel.

Success messages in group chats auto-delete after ~1 minute (60 s). In private
chat, the result message stays.

## Layout

```
bot/
  config.py            env → typed settings (pydantic-settings)
  main.py              wiring: dispatcher, routers, polling/webhook
  db/                  SQLAlchemy models + async session + repositories
  handlers/            aiogram routers (repost, wizard, chat_manage, ...)
  middlewares/         logging, throttling, access gates
  menus/               inline keyboard menu
  services/            post_builder, media_group, invite_links, chat_lookup
  utils/               formatting, telegram_links, security, callbacks
  web/                 aiohttp app: webhook endpoint + /health + control API
tests/                 pytest-asyncio
```

## Relationship to the legacy bot

sharepostbot replaces the legacy C# `CommunityBot` for the same community under
the same Telegram bot account. There is no data migration — the new bot starts
from a fresh database (users are rediscovered automatically; source chats are
re-registered once, because the legacy bot never stored a real chat id). To
bring it up:

1. Set `ADMIN_IDS=<your user id>`, `BOT_TOKEN` and
   `BOT_NAME=<bot username without @>` in `.env`.
2. Start the bot (`python -m bot`).
3. Re-register each source chat: add the bot to the chat and follow the
   onboarding buttons, or `/add_chat <link>` in PM.

## Development

```bash
ruff check bot tests
ruff format bot tests
mypy bot
pytest --cov=bot
```
