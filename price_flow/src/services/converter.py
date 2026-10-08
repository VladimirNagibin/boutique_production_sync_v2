import secrets
import time

from pathlib import Path

import requests

from common.log_context import bind_class, get_request_id
from common.request_context_middleware import REQUEST_ID_HEADER
from core.logger import get_logger
from schemas.converter_schemas import UploadResult


logger = get_logger(__name__)

MAX_RETRIES: int = 3
RETRY_BASE_DELAY_SECONDS: float = 1.0
RETRY_MAX_DELAY_SECONDS: float = 30.0
RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class FileUploader:
    def __init__(self, base_url: str = "http://converter:8000"):
        self.base_url = base_url.rstrip("/")
        self.upload_url = f"{self.base_url}/api/v1/files/send_convert"

    def upload_file(self, file_path: str | Path) -> UploadResult:
        """
        Загружает файл на сервер

        Args:
            file_path: Путь к файлу

        Returns:
            UploadResult: Результат загрузки
        """
        path = Path(file_path)
        with bind_class(self):
            return self._upload_file(path)

    def _upload_file(self, path: Path) -> UploadResult:
        """Загружает файл, прокидывая X-Request-ID в converter."""
        if not path.exists():
            logger.warning(
                "Converter upload file not found",
                extra={"file_name": path.name},
            )
            return self._failure_result(
                error_code="FILE_NOT_FOUND",
                error=f"File not found: {path}",
            )

        logger.info(
            "Starting converter upload",
            extra={"file_name": path.name},
        )
        try:
            response = self._post_file(path)
            response.raise_for_status()
            data = self._parse_response(response)
        except requests.exceptions.ConnectionError:
            logger.exception(
                "Converter connection failed",
                extra={"file_name": path.name},
            )
            return self._failure_result(
                error_code="CONNECTION_ERROR",
                error="Cannot connect to server. Make sure API is running.",
            )
        except requests.exceptions.HTTPError as error:
            status_code = (
                error.response.status_code
                if error.response is not None
                else None
            )
            response_text = (
                error.response.text if error.response is not None else ""
            )
            logger.exception(
                "Converter returned an HTTP error",
                extra={
                    "file_name": path.name,
                    "status_code": status_code,
                },
            )
            return self._failure_result(
                error_code="HTTP_ERROR",
                error=f"HTTP error: {status_code} - {response_text}",
            )
        except requests.exceptions.Timeout as error:
            logger.exception(
                "Converter upload timed out",
                extra={"file_name": path.name},
            )
            return self._failure_result(
                error_code="TIMEOUT",
                error=f"Request timed out: {error!s}",
            )
        except (ValueError, TypeError) as error:
            logger.exception(
                "Converter returned invalid response",
                extra={
                    "file_name": path.name,
                    "error_type": type(error).__name__,
                },
            )
            return self._failure_result(
                error_code="INVALID_RESPONSE",
                error=f"Invalid server response: {error!s}",
            )
        except requests.exceptions.RequestException as error:
            logger.exception(
                "Converter upload request failed",
                extra={
                    "file_name": path.name,
                    "error_type": type(error).__name__,
                },
            )
            return self._failure_result(
                error_code="REQUEST_ERROR",
                error=f"Request failed: {error!s}",
            )
        except OSError as error:
            logger.exception(
                "Converter upload file operation failed",
                extra={
                    "file_name": path.name,
                    "error_type": type(error).__name__,
                },
            )
            return self._failure_result(
                error_code="FILE_OPERATION_ERROR",
                error=f"File operation error: {error!s}",
            )

        logger.info(
            "Converter upload completed",
            extra={"file_name": path.name},
        )
        return UploadResult(
            filename=data["filename"],
            token=data["token"],
            message=data["message"],
            success=True,
        )

    def _post_file(self, path: Path) -> requests.Response:
        """Отправляет файл с ретраями для временных сетевых ошибок."""
        headers = self._build_headers()
        last_error: requests.RequestException | None = None

        for attempt in range(MAX_RETRIES):
            try:
                with Path.open(path, "rb") as file_handle:
                    files = {"file": (path.name, file_handle)}
                    response = requests.post(
                        self.upload_url,
                        files=files,
                        headers=headers or None,
                        timeout=30,
                    )
            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            ) as error:
                last_error = error
            else:
                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_error = self._retryable_http_error(response)
                else:
                    return response

            if attempt >= MAX_RETRIES - 1:
                break
            delay = self._retry_delay(attempt)
            logger.warning(
                "Converter upload attempt failed, retrying",
                extra={
                    "file_name": path.name,
                    "attempt": attempt + 1,
                    "error_type": type(last_error).__name__,
                    "backoff_seconds": round(delay, 2),
                },
            )
            time.sleep(delay)

        assert last_error is not None
        raise last_error

    @staticmethod
    def _retryable_http_error(
        response: requests.Response,
    ) -> requests.exceptions.HTTPError:
        """Создаёт HTTPError для ретраемого статуса ответа."""
        message = f"Retryable HTTP status {response.status_code}"
        return requests.exceptions.HTTPError(message, response=response)

    def _build_headers(self) -> dict[str, str]:
        """Собирает заголовки запроса, прокидывая X-Request-ID."""
        headers: dict[str, str] = {}
        request_id = get_request_id()
        if request_id:
            headers[REQUEST_ID_HEADER] = request_id
        return headers

    @staticmethod
    def _parse_response(response: requests.Response) -> dict[str, str]:
        """Разбирает JSON-ответ converter и валидирует его форму."""
        data = response.json()
        if not isinstance(data, dict):
            message = "Non-object JSON response"
            raise TypeError(message)
        return {
            "filename": data.get("filename", ""),
            "token": data.get("token", ""),
            "message": data.get("message", ""),
        }

    @staticmethod
    def _failure_result(error_code: str, error: str) -> UploadResult:
        """Формирует неудачный UploadResult со структурированным кодом."""
        return UploadResult(
            filename="",
            token="",
            message="",
            success=False,
            error=error,
            error_code=error_code,
        )

    @staticmethod
    def _retry_delay(attempt: int) -> float:
        """Экспоненциальная задержка с jitter."""
        delay = min(
            RETRY_BASE_DELAY_SECONDS * (2.0**attempt),
            RETRY_MAX_DELAY_SECONDS,
        )
        return delay * (0.5 + secrets.randbelow(1000) / 2000)

    # def check_status(self, token: str) -> dict:
    #     """
    #     Проверяет статус обработки файла

    #     Args:
    #         token: Токен полученный при загрузке

    #     Returns:
    #         dict: Статус файла
    #     """
    #     try:
    #         response = requests.get(f"{self.base_url}/api/status/{token}")
    #         return response.json()
    #     except Exception as e:
    #         return {"error": str(e)}


def get_file_uploader() -> FileUploader:
    return FileUploader()
