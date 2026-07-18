import logging

from pathlib import Path
from typing import Any, Final

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .exceptions.settings import (
    InvalidSettingsValueError,
    ProductionSettingsError,
    SettingsLoadError,
)

from .utils import LogLevel


# ===== Константы / Constants =====
ENCRYPTION_KEY_MIN_LENGTH = 44  # Минимальная длина ключа Fernet
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 МБ
SECRET_KEY_MIN_LENGTH = 32
DEFAULT_LOGGING_FILE_MAX_BYTES = 50_000_000  # 50 MB
DEFAULT_LOGGING_BACKUP_COUNT = 5
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
SEQ_DEFAULT_URL = "http://localhost:5341"

# Локальный логгер для этого модуля (без зависимости от глобальной настройки)
_logger = logging.getLogger(__name__)


# ===== Основной класс настроек приложения =====
class AppSettings(BaseSettings):
    """
    Основные настройки FastAPI приложения.

    Загружаются из переменных окружения с префиксом APP_.
    """

    # ----- Поля модели -----
    project_name: str = Field(
        default="bp_sync",
        description="Project name",
    )
    host: str = Field(
        default=DEFAULT_HOST,
        description="Server host",
    )
    port: int = Field(
        default=DEFAULT_PORT,
        ge=1,
        le=65535,
        description="Server port (1-65535)",
    )
    reload: bool = Field(
        default=False,
        description="Enable auto-reload (development only)",
    )
    log_level: LogLevel = Field(
        default=LogLevel.DEBUG,
        description="Logging level",
    )
    base_dir: Path = Field(
        default=Path(__file__).resolve().parent.parent.parent,
        description="Base directory of the application",
    )

    # Настройки файлового логирования
    log_to_file: bool = Field(
        default=True,
        description="Enable file logging",
    )
    logging_file_max_bytes: int = Field(
        default=DEFAULT_LOGGING_FILE_MAX_BYTES,
        gt=0,
        description="Maximum size of log file in bytes",
    )
    logging_backup_count: int = Field(
        default=DEFAULT_LOGGING_BACKUP_COUNT,
        ge=0,
        description="Number of backup log files to keep",
    )

    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- Валидаторы -----
    @field_validator("base_dir", mode="after")
    @classmethod
    def validate_base_dir(cls, v: Path) -> Path:
        """
        Проверяет, что базовая директория существует и является директорией.

        Args:
            v: Путь к базовой директории

        Returns:
            Проверенный путь

        Raises:
            InvalidSettingsValueError: если директория не существует
        """
        if not v.exists():
            raise InvalidSettingsValueError(
                field_name="base_dir",
                value=str(v),
                reason="Directory does not exist",
            )
        if not v.is_dir():
            raise InvalidSettingsValueError(
                field_name="base_dir",
                value=str(v),
                reason="Path is not a directory",
            )
        return v

    @field_validator("log_level", mode="before")
    @classmethod
    def validate_log_level(cls, v: Any) -> LogLevel:
        """
        Преобразует строку в LogLevel, если необходимо.

        Args:
            v: Значение уровня логирования

        Returns:
            LogLevel
        """
        if isinstance(v, LogLevel):
            return v
        if isinstance(v, str):
            try:
                return LogLevel(v.upper())
            except ValueError as e:
                raise InvalidSettingsValueError(
                    field_name="log_level",
                    value=v,
                    reason=f"Invalid log level: {e}",
                ) from e
        raise InvalidSettingsValueError(
            field_name="log_level",
            value=v,
            reason=f"Expected LogLevel or string, got {type(v).__name__}",
        )

    # ----- Прокси-свойства -----
    @property
    def is_dev(self) -> bool:
        """Возвращает True, если приложение запущено в режиме разработки."""
        return self.reload or self.log_level == LogLevel.DEBUG

    # ----- Вспомогательные публичные методы -----
    def get_log_file_path(self) -> Path:
        """
        Возвращает путь к файлу лога (создаёт директорию при необходимости).
        """
        log_dir = self.base_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir / "app.log"


# ===== Настройки Seq =====
class SeqSettings(BaseSettings):
    """
    Настройки отправки логов в Seq через HTTP API.

    Загружаются из переменных окружения с префиксом SEQ_.
    """

    # ----- Поля модели -----
    enabled: bool = Field(
        default=False,
        description="Enable Seq logging",
    )
    url: str = Field(
        default=SEQ_DEFAULT_URL,
        description="Seq server URL",
    )
    api_key: str = Field(
        default="",
        description="API key for Seq authentication",
    )
    level: str = Field(
        default=LogLevel.DEBUG,
        description="Minimum log level to send to Seq",
    )
    environment: str = Field(
        default="development",
        description="Environment name (development, staging, production)",
    )

    model_config = SettingsConfigDict(
        env_prefix="SEQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- Валидаторы -----
    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, v: Any) -> str:
        """
        Проверяет, что URL Seq имеет корректный формат.

        Args:
            v: URL Seq

        Returns:
            Проверенный URL

        Raises:
            InvalidSettingsValueError: если URL невалидный
        """
        if not isinstance(v, str):
            raise InvalidSettingsValueError(
                field_name="url",
                value=str(v),
                reason="URL must be a string",
            )
        v = v.strip()
        if not v:
            raise InvalidSettingsValueError(
                field_name="url",
                value=v,
                reason="URL cannot be empty",
            )
        # Простейшая проверка формата
        if not v.startswith(("http://", "https://")):
            raise InvalidSettingsValueError(
                field_name="url",
                value=v,
                reason="URL must start with http:// or https://",
            )
        return v

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        """
        Проверяет, что уровень логирования допустим.

        Args:
            v: Уровень логирования

        Returns:
            Проверенный уровень

        Raises:
            InvalidSettingsValueError: если уровень не поддерживается
        """
        valid_levels = {item.value for item in LogLevel}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise InvalidSettingsValueError(
                field_name="level",
                value=v,
                reason=(f"Invalid log level. Allowed: {', '.join(valid_levels)}"),
            )
        return v_upper

    # ----- Прокси-свойства -----
    @property
    def is_enabled(self) -> bool:
        """Возвращает True, если отправка в Seq включена и URL задан."""
        return self.enabled and bool(self.url) and bool(self.url.strip())


# ===== Главный класс настроек =====
class Settings(BaseSettings):
    """
    Главный класс настроек приложения.

    Загружает конфигурацию из переменных окружения и файла .env.
    Предоставляет методы для валидации production-окружения.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
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
                _logger.error("Production settings validation failed: %s", errors)
                raise ProductionSettingsError(message=", ".join(errors))
        return self

    @property
    def is_dev(self) -> bool:
        """True, если приложение запущено в development-режиме."""
        return self.app.is_dev

    # ----- Вспомогательные проверки (приватные) -----
    def _collect_production_errors(self) -> list[str]:
        """Собирает список ошибок валидации для production-окружения."""
        errors: list[str] = []
        errors.extend(self._validate_app_production())
        # errors.extend(self._validate_auth_production())
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

    # def _validate_auth_production(self) -> list[str]:
    #     """Проверяет настройки аутентификации в production."""
    #     errors: list[str] = []
    #     if (
    #         not self.auth.secret_key
    #         or len(self.auth.secret_key) < SECRET_KEY_MIN_LENGTH
    #     ):
    #         errors.append(
    #             "AUTH_SECRET_KEY is missing or too short "
    #             f"(min {SECRET_KEY_MIN_LENGTH} chars)"
    #         )
    #     return errors

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
        raise SettingsLoadError(message=f"Could not initialize settings: {e}") from e
    else:
        return instance


# Глобальный экземпляр настроек с явной аннотацией типа
settings: Final[Settings] = _load_settings()
