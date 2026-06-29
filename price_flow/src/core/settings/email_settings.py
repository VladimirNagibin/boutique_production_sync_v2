"""
Модуль настроек для подключения почты.

Содержит конфигурации для:
- gmail
- google
"""

from __future__ import annotations

import re

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.exceptions.settings import InvalidSettingsValueError


# ===== Константы =====
DEFAULT_USER_GMAIL = "user@gmail.com"
DEFAULT_PASS_GMAIL = "pass"  # noqa: S105
DEFAULT_API_KEY_GOOGLE = "postgres"


# ===== Настройки PostgreSQL =====
class EmailSettings(BaseSettings):
    """Настройки подключения к почте."""

    # ----- Поля модели -----
    user_gmail: str = Field(
        default=DEFAULT_USER_GMAIL,
        description="User gmail",
    )
    pass_gmail: str = Field(
        default=DEFAULT_PASS_GMAIL,
        description="Pass gmail",
    )
    api_key_google: str = Field(
        default=DEFAULT_API_KEY_GOOGLE,
        description="Api key google",
    )

    model_config = SettingsConfigDict(
        env_prefix="EMAIL_",
        env_file=".env.price_flow",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- Валидаторы -----
    @field_validator("user_gmail")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Проверяет, что адрес электронной почты корректен."""
        # Простое регулярное выражение для проверки формата email
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(pattern, v):
            raise InvalidSettingsValueError(
                field_name="user_gmail",
                value=v,
                reason=(
                    "Invalid email format. Expected format: user@example.com"
                ),
            )
        return v
