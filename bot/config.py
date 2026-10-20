"""Application configuration loaded from environment / .env."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Any, get_origin

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict
from pydantic_settings.sources import DotEnvSettingsSource, EnvSettingsSource

from bot import texts


class CsvEnvSettingsSource(EnvSettingsSource):
    """Env vars source with comma-separated list parsing."""

    def decode_complex_value(self, field_name: str, field: Any, value: Any) -> Any:
        annotation = getattr(field, "annotation", None)
        if isinstance(value, str) and get_origin(annotation) is list:
            return [item.strip() for item in value.split(",") if item.strip()]
        return super().decode_complex_value(field_name, field, value)


class CsvDotEnvSettingsSource(DotEnvSettingsSource):
    """.env file source with comma-separated list parsing."""

    def decode_complex_value(self, field_name: str, field: Any, value: Any) -> Any:
        annotation = getattr(field, "annotation", None)
        if isinstance(value, str) and get_origin(annotation) is list:
            return [item.strip() for item in value.split(",") if item.strip()]
        return super().decode_complex_value(field_name, field, value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Bot ---
    bot_token: str = Field(..., min_length=10)
    bot_name: str = Field(..., min_length=1)
    main_channel_id: int = Field(..., description="Target channel for posts")
    # Optional: topic (forum thread) in the main channel to post into.
    # Leave 0 to post in "General" / non-forum channel.
    main_channel_thread_id: int = 0
    # Super-admin user IDs: always STAFF regardless of DB state, so the first
    # admin can be set via env only.
    admin_ids: list[int] = Field(default_factory=list)
    debug_info_chat_ids: list[int] = Field(default_factory=list)

    # --- Webhook ---
    webhook_url: str = ""
    webhook_path: str = "/webhook"
    webhook_port: int = 8080
    webhook_secret: str = ""
    webhook_public_url: str = ""

    # --- Database ---
    db_path: Path = Path("./data/database.sqlite")

    # --- Logging ---
    log_level: str = "INFO"
    log_dir: Path = Path("./logs")
    log_json: bool = False
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5
    # Tech chat (DEBUG_INFO_CHAT_IDS): events at or above `log_chat_level` are
    # forwarded automatically ("errors" category); `log_chat_events` lists the
    # enabled categories (see bot/services/tech_chat.py).
    log_chat_level: str = "ERROR"
    log_chat_events: list[str] = Field(
        default_factory=lambda: ["errors", "system", "admin", "business"]
    )

    # --- HTTP control API ---
    http_host: str = "127.0.0.1"
    http_port: int = 8081
    http_api_password: str = ""

    # --- Features ---
    protect_content: bool = True
    # Extra trigger phrases (besides the @mention) that trigger reposting when
    # a user replies with them in a source chat. Case-insensitive, comma-separated.
    repost_trigger_phrases: list[str] = Field(
        default_factory=lambda: list(texts.DEFAULT_REPOST_TRIGGERS)
    )
    # Custom emoji ID for the community link buttons in the inline menu
    # (document_id string). Empty = no icon. Works only if the bot owner has
    # Telegram Premium or the bot purchased usernames on Fragment.
    link_icon_custom_emoji_id: str = ""

    # --- Pagination ---
    # Page sizes for the inline-menu list pagination (users and chats are
    # independent).
    list_page_users: int = Field(default=20, ge=1)
    list_page_chats: int = Field(default=20, ge=1)

    # --- Backups ---
    # Automatic local DB snapshots: one per BACKUP_INTERVAL_HOURS into
    # BACKUP_DIR, keeping the newest BACKUP_KEEP files; nothing is sent to
    # Telegram.
    backup_dir: Path = Path("./data/backups")
    backup_interval_hours: float = Field(default=24.0, gt=0)
    backup_keep: int = Field(default=14, ge=1)
    # Allow sending DB backups to Telegram (/backup_db and the menu button).
    # False = backups are made on the server only; the menu button shows a stub.
    backup_to_chat_enabled: bool = False

    # --- API session (retry on transient network errors) ---
    api_timeout_seconds: float = 30.0
    api_max_retries: int = 3
    api_retry_base_delay: float = 0.5

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # CSV-aware env/dotenv sources: `ADMIN_IDS=1,2,3` works identically in
        # shell env and in .env.
        return (
            init_settings,
            CsvEnvSettingsSource(settings_cls),
            CsvDotEnvSettingsSource(settings_cls),
            file_secret_settings,
        )

    @model_validator(mode="after")
    def _validate_webhook(self) -> Settings:
        if self.is_webhook_mode:
            if not self.webhook_secret:
                raise ValueError("WEBHOOK_SECRET is required when WEBHOOK_URL is set")
            if not self.webhook_public_url:
                raise ValueError("WEBHOOK_PUBLIC_URL is required when WEBHOOK_URL is set")
        return self

    # --- Derived helpers ---

    @cached_property
    def is_webhook_mode(self) -> bool:
        return bool(self.webhook_url)

    @cached_property
    def db_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.db_path.resolve()}"

    def is_super_admin(self, user_id: int | None) -> bool:
        """True if `user_id` is in the env-configured ADMIN_IDS bootstrap list."""
        if user_id is None:
            return False
        return user_id in self.admin_ids


def load_settings() -> Settings:
    """Load settings from env. Validates eagerly."""
    return Settings()  # type: ignore[call-arg]
