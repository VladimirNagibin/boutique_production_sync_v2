"""
Модуль настроек для работы с прайсами.

Содержит конфигурации для:
- lanset
- nulan
- opt
"""

from __future__ import annotations

import re

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.exceptions.settings import InvalidSettingsValueError


# ===== Константы =====
DEFAULT_LANSETI_PRICE_SENDER = "user@gmail.com"
DEFAULT_NULAN_PRICES_URL = "https://disk.yandex.ru/disk"
DEFAULT_NULAN_API_URL = (
    "https://cloud-api.yandex.net/v1/disk/public/resources"
)


# ===== Настройки Price =====
class PriceSettings(BaseSettings):
    """Настройки для работы с прайсами."""

    # ----- Поля модели -----
    lanceti_price_sender: str = Field(
        default=DEFAULT_LANSETI_PRICE_SENDER,
        description="Sender lanseti",
    )
    nulan_price_url: str = Field(
        default=DEFAULT_NULAN_PRICES_URL,
        description="Nulan price url",
    )
    nulan_api_url: str = Field(
        default=DEFAULT_NULAN_API_URL,
        description="Nulan api url",
    )

    model_config = SettingsConfigDict(
        env_prefix="PRICE_",
        env_file=".env.price_flow",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- Валидаторы -----
    @field_validator("lanceti_price_sender")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Проверяет, что адрес электронной почты корректен."""
        # Простое регулярное выражение для проверки формата email
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(pattern, v):
            raise InvalidSettingsValueError(
                field_name="lanceti_price_sender",
                value=v,
                reason=(
                    "Invalid email format. Expected format: user@example.com"
                ),
            )
        return v

    @field_validator("nulan_price_url")
    @classmethod
    def validate_price_url(cls, v: str) -> str:
        """
        Проверяет корректность URL для скачивания прайсов Nulan.

        Args:
            v: Значение поля.

        Returns:
            Проверенное значение.

        Raises:
            InvalidSettingsValueError: Если URL не начинается с http:// или https://.
        """
        pattern = r"^https?://[^\s/$.?#].[^\s]*$"
        if not re.match(pattern, v):
            raise InvalidSettingsValueError(
                field_name="nulan_price_url",
                value=v,
                reason="Invalid URL format. Must start with http:// or https://",
            )
        return v

    @field_validator("nulan_api_url")
    @classmethod
    def validate_api_url(cls, v: str) -> str:
        """
        Проверяет корректность URL API Яндекс.Диска.

        Args:
            v: Значение поля.

        Returns:
            Проверенное значение.

        Raises:
            InvalidSettingsValueError: Если URL не начинается с http:// или https://.
        """
        pattern = r"^https?://[^\s/$.?#].[^\s]*$"
        if not re.match(pattern, v):
            raise InvalidSettingsValueError(
                field_name="nulan_api_url",
                value=v,
                reason="Invalid URL format. Must start with http:// or https://",
            )
        return v
