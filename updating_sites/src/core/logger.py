import logging
import os

from common.logger import (
    configure_logging,
    get_logger as get_common_logger,
)
from common.settings import discover_env_file
from core.settings import settings


SERVICE_NAME = "updating_sites"

os.environ.setdefault("APP_BASE_DIR", settings.base_dir)
os.environ.setdefault("APP_LOG_LEVEL", settings.APP_LOG_LEVEL)
os.environ.setdefault(
    "APP_LOG_TO_FILE",
    str(settings.APP_LOG_TO_FILE).lower(),
)

configure_logging(env_file=discover_env_file(".env.upd_sites"))


def get_logger(module_name: str) -> logging.Logger:
    """Возвращает логгер модуля с префиксом сервиса."""
    return get_common_logger(f"{SERVICE_NAME}.{module_name}")
