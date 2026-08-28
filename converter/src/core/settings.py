import os

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки converter. Логи: APP_* и SEQ_* (common.logger)."""

    model_config = SettingsConfigDict(
        env_file=".env.converter",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )
    PROJECT_NAME: str = "converter"
    APP_RELOAD: bool = True
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = "pass"  # noqa: S105
    UPLOAD_DIR: str = os.path.join("data", "upload")
    TTL: int = 60 * 60 * 6  # TTL in seconds
    CHUNK: int = 1024
    BASE_DIR: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    APP_LOG_LEVEL: str = Field(
        default="INFO",
        validation_alias=AliasChoices("APP_LOG_LEVEL", "LOG_LEVEL"),
    )
    LOAD: int = 0
    CONVERTED: int = 1
    APP_LOGGING_FILE_MAX_BYTES: int = Field(
        default=500_000,
        ge=100_000,
        le=10_000_000,
        validation_alias=AliasChoices(
            "APP_LOGGING_FILE_MAX_BYTES",
            "LOGGING_FILE_MAX_BYTES",
        ),
        description="Maximum size of log file in bytes before rotation",
    )


settings = Settings()
