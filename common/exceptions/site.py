from __future__ import annotations

from typing import Any

from fastapi import status

from .base import BaseAppException
from .bitrix24 import BitrixApiError as CommonBitrixApiError
from .bitrix24 import BitrixAuthError as CommonBitrixAuthError
from .enums import ErrorCode


# ===== Исключения интеграций и синхронизации сайтов =====
class BitrixAuthError(CommonBitrixAuthError):
    """Ошибка аутентификации в Bitrix24."""

    def __init__(
        self,
        message: str = "Bitrix authentication failed",
        detail: dict[Any, Any] | str | None = None,
        status_code: int | None = status.HTTP_401_UNAUTHORIZED,
    ) -> None:
        """
        Инициализирует ошибку аутентификации Bitrix24.

        Args:
            message: Сообщение об ошибке.
            detail: Дополнительные детали ошибки.
            status_code: HTTP-статус ответа.
        """
        self.detail = detail
        super().__init__(
            message=message,
            details=detail,
            status_code=status_code,
        )

    def __str__(self) -> str:
        base_message = f"BitrixAuthError: {self.message}"
        if self.detail:
            return f"{base_message} | Detail: {self.detail}"
        return base_message


class BitrixApiError(CommonBitrixApiError):
    """Ошибка ответа Bitrix24 API."""

    def __init__(
        self,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        error: str = "Unknown error",
        error_description: str = "Unknown Bitrix API error",
        message: str | None = None,
    ) -> None:
        """
        Инициализирует ошибку ответа Bitrix24 API.

        Args:
            status_code: HTTP-статус ответа.
            error: Код ошибки Bitrix24.
            error_description: Описание ошибки Bitrix24.
            message: Сообщение приложения.
        """
        details = {"error": error, "error_description": error_description}
        super().__init__(
            error=error,
            error_description=error_description,
            message=message,
            details=details,
            status_code=status_code,
        )
        self.details = details

    def is_bitrix_error(self, expected_error: str) -> bool:
        """Проверяет, совпадает ли описание ошибки с ожидаемым."""
        return self.is_expected_error(expected_error)

    def __str__(self) -> str:
        return (
            f"BitrixApiError(status_code={self.status_code}, "
            f"error='{self.error}', "
            f"description='{self.error_description}')"
        )


class ConflictException(BaseAppException):
    """Исключение для конфликтующих операций."""

    def __init__(self, entity: str, external_id: str | int) -> None:
        """
        Инициализирует ошибку конфликта сущности.

        Args:
            entity: Имя сущности.
            external_id: Внешний идентификатор сущности.
        """
        self.entity = entity
        self.external_id = external_id
        super().__init__(
            error_code=ErrorCode.CONFLICT_ERROR,
            message=f"{entity} with ID: {external_id} already exists",
            details={"entity": entity, "external_id": external_id},
            status_code=status.HTTP_409_CONFLICT,
        )


class CyclicCallException(BaseAppException):
    """Исключение для обнаружения циклических вызовов."""

    def __init__(self, message: str = "Cyclic call detected") -> None:
        self.detail = message
        super().__init__(ErrorCode.CYCLIC_CALL_ERROR, message)


class DealProcessingError(BaseAppException):
    """Исключение для ошибок обработки сделки."""

    error_code: ErrorCode = ErrorCode.DEAL_PROCESSING_ERROR

    def __init__(
        self,
        message: str = "Deal processing failed",
        deal_id: int | None = None,
    ) -> None:
        self.deal_id = deal_id
        details = {"deal_id": deal_id} if deal_id is not None else None
        super().__init__(self.error_code, message, details)


class DealNotFoundError(DealProcessingError):
    """Исключение, когда сделка не найдена в Bitrix24."""

    error_code = ErrorCode.DEAL_NOT_FOUND_ERROR


class DealNotInMainFunnelError(DealProcessingError):
    """Исключение, когда сделка не находится в основной воронке."""

    error_code = ErrorCode.DEAL_NOT_IN_MAIN_FUNNEL_ERROR


class DealSyncError(DealProcessingError):
    """Исключение, возникающее при ошибке синхронизации данных сделки."""

    error_code = ErrorCode.DEAL_SYNC_ERROR


class InvalidDealStatusError(DealProcessingError):
    """Исключение для некорректного состояния сделки."""

    error_code = ErrorCode.INVALID_DEAL_STATUS_ERROR


class InvalidDealStateError(DealProcessingError):
    """Исключение для некорректного состояния сделки."""

    error_code = ErrorCode.INVALID_DEAL_STATE_ERROR


class ExternalServiceError(DealProcessingError):
    """Ошибка внешнего сервиса."""

    error_code = ErrorCode.EXTERNAL_SERVICE_ERROR


class DocumentProcessingError(DealProcessingError):
    """Исключение для ошибок при обработке документов."""

    error_code = ErrorCode.DOCUMENT_PROCESSING_ERROR


class CompanyClientNotInitializedError(DealProcessingError):
    """Исключение, когда клиент компаний не инициализирован."""

    error_code = ErrorCode.COMPANY_CLIENT_NOT_INITIALIZED_ERROR


class WebhookValidationError(BaseAppException):
    """Кастомное исключение для ошибок валидации вебхуков."""

    def __init__(
        self,
        message: str = "Webhook validation failed",
        validation_details: str | None = None,
    ) -> None:
        self.validation_details = validation_details
        details = (
            {"validation_details": validation_details}
            if validation_details is not None
            else None
        )
        super().__init__(ErrorCode.WEBHOOK_VALIDATION_ERROR, message, details)


class WebhookSecurityError(BaseAppException):
    """Кастомное исключение для ошибок безопасности вебхуков."""

    def __init__(
        self,
        message: str = "Webhook security violation",
        security_context: str | None = None,
    ) -> None:
        self.security_context = security_context
        details = (
            {"security_context": security_context}
            if security_context is not None
            else None
        )
        super().__init__(ErrorCode.WEBHOOK_SECURITY_ERROR, message, details)


class LockAcquisitionError(BaseAppException):
    """Ошибка получения блокировки."""

    def __init__(
        self,
        resource: str = "Resource",
        message: str = "Failed to acquire lock",
    ) -> None:
        self.resource = resource
        super().__init__(
            ErrorCode.LOCK_ACQUISITION_ERROR,
            f"{message} for resource: {resource}",
            {"resource": resource},
        )


class MaxRetriesExceededError(LockAcquisitionError):
    """Достигнуто максимальное количество попыток получения блокировки."""

    def __init__(self, resource: str = "Resource", max_retries: int = 0) -> None:
        self.max_retries = max_retries
        super().__init__(resource, f"Maximum retries ({max_retries}) exceeded")
        self.error_code = ErrorCode.MAX_RETRIES_EXCEEDED_ERROR
        self.details = {"resource": resource, "max_retries": max_retries}


class ValidationError(BaseAppException):
    """Кастомное исключение для ошибок валидации."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any | None = None,
    ) -> None:
        self.field = field
        self.value = value
        super().__init__(
            ErrorCode.VALIDATION_ERROR,
            message,
            {"field": field, "value": value},
            status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


class EntityNotFoundException(BaseAppException):
    """Исключение, когда сущность не найдена в БД."""

    def __init__(self, message: str = "Entity not found") -> None:
        super().__init__(
            ErrorCode.ENTITY_NOT_FOUND_ERROR,
            message,
            status_code=status.HTTP_404_NOT_FOUND,
        )


class DatabaseException(BaseAppException):
    """Ошибка работы с БД."""

    def __init__(
        self,
        error_code: str | ErrorCode = ErrorCode.DATABASE_EXCEPTION,
        message: str | None = None,
        operation: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.operation = operation
        error_details = dict(details or {})
        if operation is not None:
            error_details["operation"] = operation
        super().__init__(
            error_code,
            message or "Database exception",
            error_details or None,
        )


class SiteRequestProcessingError(BaseAppException):
    """Базовое исключение для ошибок обработки запроса с сайта."""

    error_code: ErrorCode = ErrorCode.SITE_REQUEST_PROCESSING_ERROR
    default_message = "Site request processing failed"

    def __init__(self, message: str | None = None) -> None:
        super().__init__(self.error_code, message or self.default_message)


class ManagerNotFoundError(SiteRequestProcessingError):
    """Ошибка при отсутствии доступного менеджера."""

    error_code = ErrorCode.MANAGER_NOT_FOUND_ERROR
    default_message = "Manager not found"


class DealCreationError(SiteRequestProcessingError):
    """Ошибка при создании сделки."""

    error_code = ErrorCode.DEAL_CREATION_ERROR
    default_message = "Deal creation failed"


class ContactCreationError(SiteRequestProcessingError):
    """Ошибка при создании контакта."""

    error_code = ErrorCode.CONTACT_CREATION_ERROR
    default_message = "Contact creation failed"


class ProductNotFoundError(SiteRequestProcessingError):
    """Ошибка при поиске товара."""

    error_code = ErrorCode.PRODUCT_NOT_FOUND_ERROR
    default_message = "Product not found"


class FileDownloadError(BaseAppException):
    """Исключение при скачивании файла."""

    def __init__(self, message: str = "File download failed") -> None:
        super().__init__(ErrorCode.FILE_DOWNLOAD_ERROR, message)


class ProductTransformationError(BaseAppException):
    """Ошибка при трансформации товара."""

    def __init__(self, message: str = "Product transformation failed") -> None:
        super().__init__(ErrorCode.PRODUCT_TRANSFORMATION_ERROR, message)


def create_bitrix_api_error_from_response(
    status_code: int, response_data: dict[str, Any] | None = None
) -> BitrixApiError:
    """Создает BitrixApiError на основе ответа от API."""
    if response_data:
        error = response_data.get("error", "Unknown error")
        error_description = response_data.get(
            "error_description", "No description provided"
        )
    else:
        error = "HTTP Error"
        error_description = f"Status code: {status_code}"

    return BitrixApiError(
        status_code=status_code,
        error=error,
        error_description=error_description,
    )


def should_retry_operation(exception: Exception) -> bool:
    """
    Определяет, следует ли повторять операцию при возникновении исключения.

    Returns:
        True если операцию стоит повторить, False в противном случае.
    """
    if isinstance(exception, BitrixApiError):
        status_code = exception.status_code
        return bool(
            status_code is not None
            and status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    return isinstance(exception, LockAcquisitionError)
