"""Application settings configuration using Pydantic."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    PROJECT_NAME: str = "Price Flow"

    APP_HOST: str = Field(
        default="127.0.0.1",
        description="Host to bind to. Use '0.0.0.0' only in Docker containers.",
    )

    APP_PORT: int = Field(
        default=8000,
        ge=1024,  # Не используем привилегированные порты (<1024)
        le=65535,
        description="Port to bind to (1024-65535)",
    )

    APP_RELOAD: bool = Field(
        default=True, description="Enable auto-reload. Should be False in production."
    )

    BASE_DIR: str = Field(
        default_factory=lambda: str(Path(__file__).resolve().parent.parent),
        description="Base directory of the project",
    )

    LOG_LEVEL: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    LOGGING_FILE_MAX_BYTES: int = Field(
        default=500_000,
        ge=100_000,
        le=10_000_000,
        description="Maximum size of log file in bytes before rotation",
    )

    DB_SQLITE_FILE: str = Field(
        default="data/price_flow.db",
        min_length=1,
        description="DB path for SQLite database",
    )

    @property
    def DB_SQLITE_PATH(self) -> Path:
        return Path(self.BASE_DIR) / self.DB_SQLITE_FILE

    POOL_SIZE: int = Field(
        default=1,
        gt=0,
        description="Pool size for database connections",
    )

    SECRET_KEY: str = Field(
        default="your-secret-key-change-in-production",
        min_length=32,
        description="Secret key",
    )

    USER_GMAIL: str = "user_gmail"
    PASS_GMAIL: str = ""
    API_KEY_GOOGLE: str = "api_key_google"
    SENDER_PRICE_LANSETI: str = "price@mail.ru"

    NULAN_PRICES_URL: str = "url"
    NULAN_API_URL: str = "url"

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate that LOG_LEVEL is a valid logging level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            error_message = f"LOG_LEVEL must be one of {valid_levels}"
            raise ValueError(error_message)
        return v.upper()

    model_config = SettingsConfigDict(
        env_file=".env.price_flow",
        env_file_encoding="utf-8",
        extra="ignore",
        # env_prefix="SHOP_BOT_",
    )


settings = Settings()
