import logging

from common.logger import configure_logging
from common.logger import get_logger as get_common_logger
from common.settings import discover_env_file


SERVICE_NAME = "price_flow"

configure_logging(env_file=discover_env_file(".env.price_flow"))


def get_logger(module_name: str) -> logging.Logger:
    """Возвращает логгер модуля с префиксом сервиса."""
    return get_common_logger(f"{SERVICE_NAME}.{module_name}")
