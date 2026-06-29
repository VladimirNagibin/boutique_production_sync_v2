import json

from pathlib import Path

import requests

# from core.logger import logger
from schemas.converter_schemas import UploadResult


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
        try:
            if not Path(file_path).exists():
                return UploadResult(
                    filename="",
                    token="",
                    message="",
                    success=False,
                    error=f"File not found: {file_path}",
                )

            with Path.open(Path(file_path), "rb") as f:
                files = {"file": (Path(file_path).name, f)}
                response = requests.post(self.upload_url, files=files, timeout=30)

            response.raise_for_status()
            data = response.json()

            return UploadResult(
                filename=data.get("filename", ""),
                token=data.get("token", ""),
                message=data.get("message", ""),
                success=True,
            )

        except requests.exceptions.ConnectionError:
            return UploadResult(
                filename="",
                token="",
                message="",
                success=False,
                error="Cannot connect to server. Make sure API is running.",
            )
        except requests.exceptions.HTTPError as e:
            return UploadResult(
                filename="",
                token="",
                message="",
                success=False,
                error=f"HTTP error: {e.response.status_code} - {e.response.text}",
            )
        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            return UploadResult(
                filename="",
                token="",
                message="",
                success=False,
                error=f"Request failed: {e!s}",
            )
        except OSError as e:
            return UploadResult(
                filename="",
                token="",
                message="",
                success=False,
                error=f"File operation error: {e!s}",
            )
        except json.JSONDecodeError as e:
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
