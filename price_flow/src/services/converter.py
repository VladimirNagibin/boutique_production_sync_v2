import json

from pathlib import Path

import requests

from core.logger import get_logger
from schemas.converter_schemas import UploadResult


logger = get_logger(__name__)


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
        try:
            if not path.exists():
                logger.warning(
                    "Converter upload file not found",
                    extra={"file_name": path.name},
                )
                return UploadResult(
                    filename="",
                    token="",
                    message="",
                    success=False,
                    error=f"File not found: {file_path}",
                )

            logger.info(
                "Starting converter upload",
                extra={"file_name": path.name},
            )
            with Path.open(path, "rb") as f:
                files = {"file": (path.name, f)}
                response = requests.post(
                    self.upload_url, files=files, timeout=30
                )

            response.raise_for_status()
            data = response.json()
            logger.info(
                "Converter upload completed",
                extra={"file_name": path.name},
            )

            return UploadResult(
                filename=data.get("filename", ""),
                token=data.get("token", ""),
                message=data.get("message", ""),
                success=True,
            )

        except requests.exceptions.ConnectionError:
            logger.exception(
                "Converter connection failed",
                extra={"file_name": path.name},
            )
            return UploadResult(
                filename="",
                token="",
                message="",
                success=False,
                error="Cannot connect to server. Make sure API is running.",
            )
        except requests.exceptions.HTTPError as e:
            logger.exception(
                "Converter returned an HTTP error",
                extra={
                    "file_name": path.name,
                    "status_code": e.response.status_code,
                },
            )
            return UploadResult(
                filename="",
                token="",
                message="",
                success=False,
                error=(
                    f"HTTP error: {e.response.status_code} - {e.response.text}"
                ),
            )
        except (
            requests.exceptions.Timeout,
            requests.exceptions.RequestException,
        ) as e:
            logger.exception(
                "Converter upload request failed",
                extra={
                    "file_name": path.name,
                    "error_type": type(e).__name__,
                },
            )
            return UploadResult(
                filename="",
                token="",
                message="",
                success=False,
                error=f"Request failed: {e!s}",
            )
        except OSError as e:
            logger.exception(
                "Converter upload file operation failed",
                extra={
                    "file_name": path.name,
                    "error_type": type(e).__name__,
                },
            )
            return UploadResult(
                filename="",
                token="",
                message="",
                success=False,
                error=f"File operation error: {e!s}",
            )
        except json.JSONDecodeError as e:
            logger.exception(
                "Converter returned invalid JSON",
                extra={
                    "file_name": path.name,
                    "error_type": type(e).__name__,
                },
            )
            return UploadResult(
                filename="",
                token="",
                message="",
                success=False,
                error=f"Invalid server response: {e!s}",
            )

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
