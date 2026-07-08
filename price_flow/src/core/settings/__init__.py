import logging

from typing import Final

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.exceptions.settings import (
    InvalidSettingsValueError,
    ProductionSettingsError,
    SettingsLoadError,
)

from .auth import SECRET_KEY_MIN_LENGTH, AuthSettings
from .base import AppSettings, SeqSettings
from .database import (
    DatabaseSettings,
    RabbitSettings,
    RedisSettings,
    SqliteSettings,
)
from .email_settings import EmailSettings
from .price import PriceSettings
from .utils import LogLevel


# ===== Константы / Constants =====
ENCRYPTION_KEY_MIN_LENGTH = 44  # Минимальная длина ключа Fernet
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 МБ
# from .ai import AISettings
# from .business import BusinessSettings
# from .messaging import EmailSettings

# Локальный логгер для этого модуля (без зависимости от глобальной настройки)
_logger = logging.getLogger(__name__)


# ===== Главный класс настроек =====
class Settings(BaseSettings):
    """
    Главный класс настроек приложения.

    Загружает конфигурацию из переменных окружения и файла .env.
    Предоставляет методы для валидации production-окружения.
    """

    model_config = SettingsConfigDict(
        env_file=".env.price_flow",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- Секции настроек -----
    app: AppSettings = Field(
        default_factory=AppSettings, description="Настройки приложения"
    )
    seq: SeqSettings = Field(
        default_factory=SeqSettings, description="Настройки Seq (логирование)"
    )
    database: DatabaseSettings = Field(
        default_factory=DatabaseSettings, description="Настройки БД"
    )
    sqlite: SqliteSettings = Field(
        default_factory=SqliteSettings, description="Настройки Sqlite"
    )
    redis: RedisSettings = Field(
        default_factory=RedisSettings, description="Настройки Redis"
    )
    rabbitmq: RabbitSettings = Field(
        default_factory=RabbitSettings, description="Настройки RabbitMQ"
    )
    auth: AuthSettings = Field(
        default_factory=AuthSettings, description="Настройки аутентификации"
    )
    email: EmailSettings = Field(
        default_factory=EmailSettings, description="Настройки почты"
    )
    price: PriceSettings = Field(
        default_factory=PriceSettings, description="Настройки прайсов"
    )

    # # ----- AI/ML -----
    # ai: AISettings = Field(default_factory=AISettings)

    # # ----- Бизнес-логика -----
    # business: BusinessSettings = Field(default_factory=BusinessSettings)

    # ----- Глобальные настройки -----
    encryption_key: str = Field(
        default="your-fernet-key-generated-by-cryptography.fernet.Fernet.generate_key",
        min_length=ENCRYPTION_KEY_MIN_LENGTH,
    )  # Fernet key
    max_file_size: int = Field(
        default=MAX_FILE_SIZE,
        description="Максимальный размер загружаемого файла в байтах",
    )

    # ----- Валидаторы -----
    @field_validator("encryption_key")
    @classmethod
    def _validate_encryption_key(cls, v: str) -> str:
        """
        Проверяет корректность ключа шифрования.
        Должна быть проверка формата Fernet, но ограничиваемся длиной.
        """
        if len(v) < ENCRYPTION_KEY_MIN_LENGTH:
            raise InvalidSettingsValueError(
                field_name="encryption_key",
                value=v,
                reason=(
                    f"Encryption key must be at least "
                    f"{ENCRYPTION_KEY_MIN_LENGTH} characters long"
                ),
            )
        # Дополнительно можно проверить, что ключ выглядит как base64 и т.п.
        return v

    @model_validator(mode="after")
    def _check_production_on_load(self) -> "Settings":
        """
        Автоматически проверяет production-настройки при загрузке,
        если приложение не в dev-режиме.
        """
        if not self.is_dev:
            # В production режиме выполняем валидацию и бросаем исключение
            # при ошибках
            errors = self._collect_production_errors()
            if errors:
                _logger.error(
                    "Production settings validation failed: %s", errors
                )
                raise ProductionSettingsError(message=", ".join(errors))
        return self

    # ----- Прокси-свойства -----
    @property
    def dsn(self) -> str:
        """DSN для подключения к базе данных."""
        return self.database.dsn

    @property
    def is_dev(self) -> bool:
        """True, если приложение запущено в development-режиме."""
        return self.app.is_dev

    # ----- Вспомогательные проверки (приватные) -----
    def _collect_production_errors(self) -> list[str]:
        """Собирает список ошибок валидации для production-окружения."""
        errors: list[str] = []
        errors.extend(self._validate_app_production())
        errors.extend(self._validate_auth_production())
        errors.extend(self._validate_encryption_production())
        return errors

    def _validate_app_production(self) -> list[str]:
        """Проверяет настройки приложения в production."""
        errors: list[str] = []
        if self.app.reload:
            errors.append("APP_RELOAD must be False in production")
        if self.app.log_level == "DEBUG":
            errors.append("LOG_LEVEL must not be DEBUG in production")
        return errors

    def _validate_auth_production(self) -> list[str]:
        """Проверяет настройки аутентификации в production."""
        errors: list[str] = []
        if (
            not self.auth.secret_key
            or len(self.auth.secret_key) < SECRET_KEY_MIN_LENGTH
        ):
            errors.append(
                "AUTH_SECRET_KEY is missing or too short "
                f"(min {SECRET_KEY_MIN_LENGTH} chars)"
            )
        return errors

    def _validate_encryption_production(self) -> list[str]:
        """Проверяет настройки шифрования в production."""
        errors: list[str] = []
        if (
            not self.encryption_key
            or len(self.encryption_key) < ENCRYPTION_KEY_MIN_LENGTH
        ):
            errors.append(
                "ENCRYPTION_KEY is missing or too short "
                f"(min {ENCRYPTION_KEY_MIN_LENGTH} chars)"
            )
        return errors

    # ----- Публичные методы валидации -----
    def validate_production(self) -> None:
        """
        Выполняет полную валидацию настроек для production-окружения.

        Raises:
            ProductionSettingsError: если найдены ошибки в настройках.
        """
        errors = self._collect_production_errors()
        if errors:
            _logger.error("Production validation failed: %s", errors)
            raise ProductionSettingsError(message=", ".join(errors))
        _logger.info("Production settings are valid")


# ===== Создание глобального экземпляра =====
def _load_settings() -> Settings:
    """
    Загружает настройки приложения.

    Returns:
        Settings: Экземпляр настроек

    Raises:
        SettingsLoadError: Если не удалось загрузить настройки
    """
    try:
        instance = Settings()
        _logger.debug("Settings loaded successfully")
    except Exception as e:
        _logger.critical("Failed to load settings: %s", e, exc_info=True)
        raise SettingsLoadError(
            message=f"Could not initialize settings: {e}"
        ) from e
    else:
        return instance


# Глобальный экземпляр настроек с явной аннотацией типа
settings: Final[Settings] = _load_settings()


# ===== Экспортируемые объекты =====
__all__ = [
    "AppSettings",
    "AuthSettings",
    # "Bitrix24Settings",
    "DatabaseSettings",
    "LogLevel",
    "ProductionSettingsError",
    "RedisSettings",
    "Settings",
    "SettingsLoadError",
    "settings",
]
