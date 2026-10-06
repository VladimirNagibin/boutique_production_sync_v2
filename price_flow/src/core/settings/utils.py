"""
Утилиты для модуля настроек.

Содержит вспомогательные классы, функции и константы для работы с настройками:
- уровень логирования (LogLevel)
- построение URL подключения к БД (DatabaseURL)
- валидация целых положительных чисел
Все сообщения об ошибках на английском, комментарии и docstrings на русском.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from common.exceptions.settings import InvalidSettingsValueError


# ===== Перечисление уровней логирования =====
class LogLevel(StrEnum):
    """Допустимые уровни логирования в приложении."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ===== Построитель URL для подключения к базе данных =====
class DatabaseURL:
    """Утилитарный класс для формирования DSN строки подключения к БД."""

    @staticmethod
    def build(
        driver: str,
        user: str,
        password: str,
        host: str,
        port: int,
        database: str,
        **kwargs: Any,
    ) -> str:
        """
        Строит DSN строку подключения к базе данных.

        Формат: driver://user:password@host:port/database?param1=value1&...

        Args:
            driver: Драйвер БД (например, postgresql, mysql)
            user: Имя пользователя
            password: Пароль
            host: Хост БД
            port: Порт
            database: Имя базы данных
            **kwargs: Дополнительные параметры подключения

        Returns:
            Сформированная DSN строка

        Example:
            >>> DatabaseURL.build(
            ...     driver="postgresql",
            ...     user="app",
            ...     password="secret",
            ...     host="localhost",
            ...     port=5432,
            ...     database="mydb",
            ...     sslmode="require",
            ... )
            'postgresql://app:secret@localhost:5432/mydb?sslmode=require'
        """
        # Формируем строку параметров запроса
        query_params = "&".join(f"{k}={v}" for k, v in kwargs.items())
        query = f"?{query_params}" if query_params else ""

        return f"{driver}://{user}:{password}@{host}:{port}/{database}{query}"


# ===== Валидаторы =====
def validate_positive_int(field_name: str, v: int) -> int:
    """
    Проверяет, что целое число положительное (> 0).

    Args:
        field_name: Имя поля (для сообщения об ошибке)
        v: Проверяемое значение

    Returns:
        Проверенное значение (без изменений)

    Raises:
        InvalidSettingsValueError: если значение меньше или равно 0
    """
    if v <= 0:
        raise InvalidSettingsValueError(
            field_name=field_name,
            value=v,
            reason="Value must be positive",
        )
    return v
