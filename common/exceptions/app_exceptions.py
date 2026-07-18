from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any

from .base import BaseAppException


if TYPE_CHECKING:
    from .enums import ErrorCode


class DatabaseAppError(BaseAppException):
    """Ошибка работы с БД."""

    def __init__(
        self,
        message: str | None = None,
        error_code: str | ErrorCode = "ERROR_WORKING_WITH_DB",
    ):
        message = message or "Ошибка работы с БД"
        super().__init__(error_code=error_code, message=message)


class DatabaseLoadError(DatabaseAppError):
    """Ошибка загрузки данных в БД."""

    def __init__(
        self,
        message: str | None = None,
    ):
        message = message or "Ошибка загрузки данных в БД"
        super().__init__(error_code="ERROR_LOADING_DATA_TO_DB", message=message)


class DataProcessingError(BaseAppException):
    """Ошибка обработки данных."""

    def __init__(
        self,
        message: str | None = None,
    ):
        message = message or "Ошибка обработки данных"
        super().__init__(error_code="DATA_PROCESSING_ERROR", message=message)


class PriceProcessingError(BaseAppException):
    """Базовая ошибка обработки прайс-листа."""

    def __init__(
        self,
        error_code: str = "PRICE_PROCESSING_ERROR",
        message: str | None = None,
        details: Any | None = None,
    ):
        message = message or "Ошибка обработки прайс-листа"
        super().__init__(error_code, message, details)


class EmailFetchError(PriceProcessingError):
    """Ошибка при получении почты или парсинге письма."""

    def __init__(
        self,
        error_code: str = "EMAIL_FETCH_ERROR",
        message: str | None = None,
        details: Any | None = None,
    ):
        message = message or "Ошибка при получении почты или парсинге письма"
        super().__init__(error_code, message, details)


class DriveApiError(PriceProcessingError):
    """Ошибка при работе с Google Drive API."""

    def __init__(
        self,
        error_code: str = "DRIVE_API_ERROR",
        message: str | None = None,
        details: Any | None = None,
    ):
        message = message or "Ошибка при работе с Google Drive API"
        super().__init__(error_code, message, details)


class ExcelProcessingError(PriceProcessingError):
    """Ошибка при чтении или записи Excel."""

    def __init__(
        self,
        error_code: str = "EXCEL_PROCESSING_ERROR",
        message: str | None = None,
        details: Any | None = None,
    ):
        message = message or "Ошибка при чтении или записи Excel"
        super().__init__(error_code, message, details)


class SupplierDataError(PriceProcessingError):
    """Ошибка при чтении или записи данных поставщика."""

    def __init__(
        self,
        error_code: str = "SUPPLIER_DATA_ERROR",
        message: str | None = None,
        details: Any | None = None,
    ):
        message = message or "Ошибка при чтении или записи данных поставщика"
        super().__init__(error_code, message, details)


class DownloadError(BaseAppException):
    """Ошибка при скачивании файла."""

    def __init__(
        self,
        error_code: str = "DOWNLOAD_ERROR",
        message: str | None = None,
        details: Any | None = None,
    ):
        message = message or "Ошибка при скачивании файла"
        super().__init__(error_code, message, details)


class ApiError(BaseAppException):
    """Ошибка при работе с API."""

    def __init__(
        self,
        error_code: str = "API_ERROR",
        message: str | None = None,
        details: Any | None = None,
    ):
        message = message or "Ошибка при работе с API"
        super().__init__(error_code, message, details)


class ErrorMessages(StrEnum):
    """
    Перечисление текстовых сообщений об ошибках.
    """

    ERR_MSG_NOT_ZIP = "Файл должен быть в формате ZIP"
    ERR_MSG_INVALID_ZIP = "Файл не является валидным ZIP архивом"
    ERR_MSG_SIZE_LIMIT = "Размер файла превышает лимит"
    ERR_MSG_SAVE_FAILED = "Ошибка при сохранении файла"
    ERR_MSG_VALIDATION_FAILED = "Ошибка при проверке ZIP архива"
    ERR_MSG_CSV_NOT_FOUND = "CSV файл не найден внутри архива"
    ERR_MSG_UNZIP_FAILED = "Не удалось распаковать архив"

    @property
    def code(self) -> str:
        """Возвращает код ошибки на основе имени."""
        return self.name
