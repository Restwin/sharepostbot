"""Structured logging via structlog with secret filtering.

Configurable via Settings:
- LOG_LEVEL: DEBUG/INFO/WARNING/ERROR (default INFO)
- LOG_DIR: directory for log files (default ./logs)
- LOG_JSON: emit JSON to stderr instead of pretty console (for production)
- LOG_MAX_BYTES: max size of each log file before rotation (default 10 MB)
- LOG_BACKUP_COUNT: number of rotated files to keep (default 5)
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import structlog

_SENSITIVE_KEYS = {
    "password",
    "passwordhash",
    "token",
    "authorization",
    "secret",
    "webhook_secret",
    "http_api_password",
    "bot_token",
}


def _redact_value(value: Any) -> Any:
    if isinstance(value, str) and len(value) > 8:
        return value[:2] + "***" + value[-2:]
    return "***"


def _redact_keys(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    for key in list(event_dict):
        if key.lower() in _SENSITIVE_KEYS:
            event_dict[key] = _redact_value(event_dict[key])
        elif isinstance(event_dict[key], dict):
            for inner in list(event_dict[key]):
                if inner.lower() in _SENSITIVE_KEYS:
                    event_dict[key][inner] = _redact_value(event_dict[key][inner])
    return event_dict


def _make_redact_secret_values(secrets: Iterable[str]) -> Any:
    """Replace known secret values inside rendered strings.

    API errors often embed the request URL (which contains the bot token) or
    echoed payloads; the key-based filter above cannot catch those.
    """
    values = sorted({s for s in secrets if s and len(s) >= 8}, key=len, reverse=True)

    def _redact(_logger: Any, _method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        if not values:
            return event_dict
        for key, value in list(event_dict.items()):
            if isinstance(value, str):
                for secret in values:
                    value = value.replace(secret, "<redacted>")
                event_dict[key] = value
        return event_dict

    return _redact


def configure_logging(
    level: str,
    log_dir: Path,
    *,
    log_json: bool = False,
    log_max_bytes: int = 10 * 1024 * 1024,
    log_backup_count: int = 5,
    secrets: Iterable[str] = (),
    extra_processor: Callable[[Any, str, dict[str, Any]], dict[str, Any]] | None = None,
) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "bot.log"
    level_num = getattr(logging, level.upper(), logging.INFO)

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        timestamper,
        _redact_keys,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _make_redact_secret_values(secrets),
    ]

    if log_json:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    # extra_processor runs after redaction and exception rendering, so it sees
    # sanitized, ready-to-forward records (e.g. the tech-chat sink).
    processors: list[Any] = [*shared_processors]
    if extra_processor is not None:
        processors.append(extra_processor)
    processors.append(renderer)

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(level_num),
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
        cache_logger_on_first_use=True,
    )

    # rotating file handler keeps bot.log from growing without bound in
    # long-running containers
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level_num)
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root = logging.getLogger()
    # avoid duplicate handlers if configure_logging is called twice
    for h in list(root.handlers):
        if isinstance(h, (RotatingFileHandler, logging.FileHandler)):
            root.removeHandler(h)
    root.addHandler(file_handler)
    root.setLevel(level_num)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
