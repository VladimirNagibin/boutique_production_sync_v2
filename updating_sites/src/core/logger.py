import logging

from common.logger import get_logger as get_common_logger


SERVICE_NAME = "updating_sites"


def get_logger(module_name: str) -> logging.Logger:
    """Возвращает логгер модуля с префиксом сервиса."""
    return get_common_logger(f"{SERVICE_NAME}.{module_name}")
