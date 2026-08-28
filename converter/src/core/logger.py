import logging
import os

from common.logger import (
    configure_logging,
    get_logger as get_common_logger,
)
from common.settings import discover_env_file
from core.settings import settings


SERVICE_NAME = "converter"

os.environ.setdefault("APP_BASE_DIR", settings.BASE_DIR)
os.environ.setdefault("APP_LOG_LEVEL", settings.APP_LOG_LEVEL)
os.environ.setdefault(
    "APP_LOGGING_FILE_MAX_BYTES",
    str(settings.APP_LOGGING_FILE_MAX_BYTES),
)

configure_logging(env_file=discover_env_file(".env.converter"))


def get_logger(module_name: str) -> logging.Logger:
    """Возвращает логгер модуля. Имя: `{SERVICE_NAME}.{module_name}`."""
    return get_common_logger(f"{SERVICE_NAME}.{module_name}")
