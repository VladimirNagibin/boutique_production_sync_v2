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

from common.exceptions.settings import InvalidSettingsValueError


# ===== Константы =====
DEFAULT_LANSET_PRICE_SENDER = "user@gmail.com"
DEFAULT_NULAN_PRICES_URL = "https://disk.yandex.ru/disk"
DEFAULT_NULAN_API_URL = "https://cloud-api.yandex.net/v1/disk/public/resources"
DEFAULT_OPT_BLANK_URL = "https://opt-centre.ru/blank-zakaza"
HTTP_URL_PATTERN = r"^https?://[^\s/$.?#].[^\s]*$"


# ===== Настройки Price =====
class PriceSettings(BaseSettings):
    """Настройки для работы с прайсами."""

    # ----- Поля модели -----
    lanset_price_sender: str = Field(
        default=DEFAULT_LANSET_PRICE_SENDER,
        description="Sender lanseti",
    )
    nulan_prices_url: str = Field(
        default=DEFAULT_NULAN_PRICES_URL,
        description="Nulan price url",
    )
    nulan_api_url: str = Field(
        default=DEFAULT_NULAN_API_URL,
        description="Nulan api url",
    )
    opt_blank_url: str = Field(
        default=DEFAULT_OPT_BLANK_URL,
        description="Opt-centre blank-zakaza page URL",
    )

    model_config = SettingsConfigDict(
        env_prefix="PRICE_",
        env_file=".env.price_flow",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- Валидаторы -----
    @field_validator("lanset_price_sender")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Проверяет, что адрес электронной почты корректен."""
        # Простое регулярное выражение для проверки формата email
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(pattern, v):
            raise InvalidSettingsValueError(
                field_name="lanset_price_sender",
                value=v,
                reason=(
                    "Invalid email format. Expected format: user@example.com"
                ),
            )
        return v

    @field_validator("nulan_prices_url")
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
        return cls._validate_http_url("nulan_price_url", v)

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
        return cls._validate_http_url("nulan_api_url", v)

    @field_validator("opt_blank_url")
    @classmethod
    def validate_opt_blank_url(cls, v: str) -> str:
        """
        Проверяет корректность URL страницы бланка Opt.

        Args:
            v: Значение поля.

        Returns:
            Проверенное значение.

        Raises:
            InvalidSettingsValueError: Если URL не начинается с http:// или https://.
        """
        return cls._validate_http_url("opt_blank_url", v)

    @staticmethod
    def _validate_http_url(field_name: str, value: str) -> str:
        """Проверяет, что значение — HTTP(S) URL."""
        if not re.match(HTTP_URL_PATTERN, value):
            raise InvalidSettingsValueError(
                field_name=field_name,
                value=value,
                reason=(
                    "Invalid URL format. Must start with http:// or https://"
                ),
            )
        return value
