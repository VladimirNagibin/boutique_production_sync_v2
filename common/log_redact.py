"""Маскирование секретов и query-строк в полях логов."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse, urlunparse

_SAFE_KEYS = frozenset(
    {
        "class_name",
        "correlation_id",
        "file_id",
        "file_name",
        "job_name",
        "method_name",
        "module_name",
        "original_file_name",
        "request_id",
        "run_id",
        "stage",
        "token_name",
    }
)
_SECRET_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "access_key",
)
_URL_RE = re.compile(r"https?://[^\s\"']+", re.IGNORECASE)
_SECRET_ASSIGN_RE = re.compile(
    r"(?i)(password|passwd|secret|token|authorization|api[_-]?key)\s*[:=]\s*[^\s&;]+"
)
_QUERY_REDACTED = "redacted"


def redact_url(url: str) -> str:
    """Убирает query/fragment у URL, чтобы не утекли токены из query."""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url
    if not parsed.query and not parsed.fragment:
        return url
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            _QUERY_REDACTED if parsed.query else "",
            "",
        )
    )


def redact_text(text: str) -> str:
    """Маскирует URL с query и пары password=/token= в произвольной строке."""
    redacted_urls = _URL_RE.sub(lambda match: redact_url(match.group(0)), text)
    return _SECRET_ASSIGN_RE.sub(r"\1=[REDACTED]", redacted_urls)


def _is_secret_field_name(key: str) -> bool:
    """True, если имя поля само по себе означает секрет, а не просто содержит token."""
    key_lower = key.lower()
    if key_lower in _SAFE_KEYS or key in _SAFE_KEYS:
        return False
    for part in _SECRET_KEY_PARTS:
        if (
            key_lower == part
            or key_lower.endswith(f"_{part}")
            or key_lower.startswith(f"{part}_")
        ):
            return True
    return False


def redact_key_value(key: str, value: str) -> str:
    """Маскирует значение, если имя поля похоже на секрет, иначе redact_text."""
    if _is_secret_field_name(key):
        return "[REDACTED]"
    return redact_text(value)


def is_safe_log_key(key: str) -> bool:
    """True, если поле не нужно маскировать по имени."""
    return key in _SAFE_KEYS


def redact_log_value(key: str, value: Any) -> Any:
    """Рекурсивно маскирует строки, словари и списки в extra."""
    if isinstance(value, str):
        return redact_key_value(key, value)
    if isinstance(value, dict):
        return {str(k): redact_log_value(str(k), v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact_log_value(key, item) for item in value]
    return value
