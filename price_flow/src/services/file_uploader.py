import asyncio
import uuid
import zipfile

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import aiofiles

from fastapi import UploadFile

from core.exceptions.enums import ErrorMessages
from core.exceptions.file import (
    FileNotZipError,
    FileSystemError,
    FileTooLargeError,
    ZipExtractionError,
)
from core.logger import logger
from core.settings import settings
from schemas.response_schemas import SuccessResponse


# ===== Константы =====
DEFAULT_UPLOAD_DIR: Final[str] = "uploads"
DEFAULT_MAX_FILE_SIZE: Final[int] = 100 * 1024 * 1024  # 100 MB
CHUNK_SIZE: Final[int] = 1024 * 1024  # 1 MB


class FileUploader:
    """
    Асинхронный загрузчик файлов с валидацией ZIP-архивов.
    """

    def __init__(
        self,
        upload_dir: str | None = None,
        max_file_size: int | None = None,
    ) -> None:
        """
        Инициализирует загрузчик.

        Args:
            upload_dir: Директория для сохранения файлов
            (по умолчанию 'uploads').
            max_file_size: Максимальный размер файла в байтах.
        """
        self._upload_dir: Path = settings.app.base_dir / Path(
            upload_dir or DEFAULT_UPLOAD_DIR
        )
        self._max_file_size: int = int(max_file_size or DEFAULT_MAX_FILE_SIZE)

        self._upload_dir.mkdir(parents=True, exist_ok=True)
        logger.info(
            "FileUploader initialized",
            extra={
                "upload_dir": str(self._upload_dir),
                "max_file_size": self._max_file_size,
            },
        )

    async def upload_file(
        self, file: UploadFile, save_subpath: str | None = None
    ) -> SuccessResponse:
        """
        Асинхронно сохраняет загруженный ZIP-файл с проверками.

        Args:
            file: Загружаемый файл (UploadFile).
            save_subpath: Поддиректория внутри upload_dir.

        Returns:
            SuccessResponse с деталями сохранённого файла.

        Raises:
            FileNotZipError: Если файл не имеет расширения .zip.
            FileTooLargeError: Если файл превышает лимит размера.
            ZipExtractionError: Если файл не является валидным ZIP-архивом.
            FileSystemError: При ошибках записи на диск.
        """
        original_name = file.filename or "unknown_upload.zip"
        logger.info(
            "Starting file upload",
            extra={"filename": original_name, "subpath": save_subpath},
        )

        # 1. Валидация расширения
        self._validate_extension(file)

        # 2. Подготовка директории и имени
        save_dir = self._get_save_directory(save_subpath)
        unique_name = self._generate_unique_filename(original_name)
        file_path = save_dir / unique_name

        try:
            # 3. Сохранение с проверкой размера
            file_size = await self._save_file_with_size_check(
                file=file, file_path=file_path
            )

            # 4. Проверка ZIP-архива (синхронная, в потоке)
            zip_info = await self._validate_zip_file(file_path)

            # 5. Формирование ответа
            file_info = self._build_file_info(
                original_filename=original_name,
                saved_filename=unique_name,
                file_path=file_path,
                file_size=file_size,
                zip_info=zip_info,
            )

            logger.info(
                "File uploaded successfully",
                extra={"path": str(file_path), "size": file_size},
            )
            return SuccessResponse(
                message="ZIP file uploaded successfully",
                details=file_info,
            )

        except (FileTooLargeError, ZipExtractionError, FileNotZipError) as e:
            # Ожидаемые ошибки бизнес-логики – логируем и пробрасываем
            logger.warning(
                "File validation failed",
                extra={"filename": original_name, "error": str(e)},
            )
            await self._safe_remove_file(file_path)
            raise

        except Exception as e:
            # Непредвиденные системные ошибки
            logger.error(
                "Unexpected error during file upload",
                extra={"filename": original_name, "error": str(e)},
                exc_info=True,
            )
            await self._safe_remove_file(file_path)
            raise FileSystemError(
                message=ErrorMessages.SAVE_FAILED.message,
                details={"original_error": str(e)},
            ) from e

    # ----- Приватные методы -----

    def _validate_extension(self, file: UploadFile) -> None:
        """
        Проверяет расширение файла (.zip).

        Raises:
            FileNotZipError: Если расширение не .zip.
        """
        if not file.filename or not file.filename.lower().endswith(".zip"):
            logger.warning(
                "Invalid file extension",
                extra={"filename": file.filename},
            )
            raise FileNotZipError(
                path=file.filename or "unknown",
                message=ErrorMessages.NOT_ZIP.message,
            )

    def _get_save_directory(self, save_subpath: str | None = None) -> Path:
        """
        Создает и возвращает безопасный путь для сохранения файла

        Args:
            save_subpath: Опциональный подпуть

        Returns:
            Path: Директория для сохранения
        """
        if save_subpath:
            # Очищаем путь от потенциально опасных символов
            safe_subpath = Path(save_subpath).name
            save_dir: Path = self._upload_dir / safe_subpath
        else:
            save_dir = Path(self._upload_dir)

        # Создаем директорию если ее нет
        save_dir.mkdir(parents=True, exist_ok=True)
        return save_dir

    def _generate_unique_filename(self, original_filename: str) -> str:
        """
        Генерирует уникальное имя файла с timestamp и UUID

        Args:
            original_filename: Оригинальное имя файла

        Returns:
            str: Уникальное имя файла
        """
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        uuid_part = uuid.uuid4().hex[:8]

        # Очищаем оригинальное имя файла от потенциально опасных символов
        safe_filename = Path(original_filename).name

        return f"{timestamp}_{uuid_part}_{safe_filename}"

    async def _save_file_with_size_check(
        self, file: UploadFile, file_path: Path
    ) -> int:
        """
        Асинхронно сохраняет файл с проверкой размера

        Args:
            file: Загружаемый файл
            file_path: Путь для сохранения

        Returns:
            int: Размер сохраненного файла в байтах

        Raises:
            FileTooLargeError: Если размер файла превышает лимит
             FileSystemError: При ошибках записи.
        """
        file_size = 0

        try:
            async with aiofiles.open(file_path, "wb") as buffer:
                while chunk := await file.read(CHUNK_SIZE):
                    file_size += len(chunk)
                    self._check_size_limit(file_path, file_size)
                    await buffer.write(chunk)
        except FileTooLargeError:
            # Пробрасываем дальше, чтобы удалить файл в блоке выше
            raise
        except OSError as e:
            # Ошибки диска (нет места, права доступа)
            logger.error(
                "Disk write error",
                extra={"path": str(file_path), "error": str(e)},
            )
            raise FileSystemError(
                message=ErrorMessages.SAVE_FAILED.message,
                details={"path": str(file_path), "error": str(e)},
            ) from e

        return file_size

    def _check_size_limit(self, file_path: Path, current_size: int) -> None:
        """
        Проверяет, не превышен ли лимит размера.

        Raises:
            FileTooLargeError: Если лимит превышен.
        """
        if current_size > self._max_file_size:
            limit_mb = self._max_file_size / (1024 * 1024)
            logger.warning(
                "File size limit exceeded",
                extra={
                    "current_size": current_size,
                    "max_size": self._max_file_size,
                },
            )
            error_message = (
                f"{ErrorMessages.SIZE_LIMIT.message} ({limit_mb:.2f}MB)"
            )
            raise FileTooLargeError(
                file_path,
                file_size=current_size,
                message=error_message,
                max_file_size=self._max_file_size,
            )

    async def _validate_zip_file(self, file_path: Path) -> dict[str, Any]:
        """
        Проверяет, является ли файл валидным ZIP архивом

        Args:
            file_path: Путь к файлу для проверки

        Returns:
            dict: Информация о содержимом ZIP архива

        Raises:
            ZipExtractionError: Если файл не является валидным ZIP архивом
        """

        def _extract_zip_info() -> dict[str, Any]:
            try:
                with zipfile.ZipFile(file_path, "r") as zip_ref:
                    file_list = zip_ref.namelist()
                    return {
                        "total_files": len(file_list),
                        "files_sample": file_list[:10],  # Ограничиваем вывод
                        "is_valid": True,
                        "compressed_size": file_path.stat().st_size,
                        "comment": (
                            zip_ref.comment.decode("utf-8", errors="ignore")
                            if zip_ref.comment
                            else None
                        ),
                    }
            except zipfile.BadZipFile as e:
                raise ZipExtractionError(
                    path=file_path,
                    message=f"Invalid ZIP file: {e}",
                ) from e
            except OSError as e:
                raise ZipExtractionError(
                    path=file_path,
                    message=f"Failed to read ZIP file: {e}",
                ) from e

        try:
            return await asyncio.to_thread(_extract_zip_info)
        except ZipExtractionError:
            # Пробрасываем кастомное исключение
            raise
        except Exception as e:
            # Любая другая ошибка – оборачиваем в ZipExtractionError
            raise ZipExtractionError(
                path=file_path,
                message=f"Unexpected error during ZIP validation: {e}",
            ) from e

    def _build_file_info(
        self,
        original_filename: str,
        saved_filename: str,
        file_path: Path,
        file_size: int,
        zip_info: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Собирает информацию о сохраненном файле

        Args:
            original_filename: Оригинальное имя файла
            saved_filename: Сохраненное имя файла
            file_path: Полный путь к файлу
            file_size: Размер файла в байтах
            zip_info: Информация о ZIP архиве

        Returns:
            dict: Структурированная информация о файле
        """
        return {
            "original_filename": original_filename,
            "saved_filename": saved_filename,
            "file_path": str(file_path),
            "file_size": file_size,
            "size_mb": round(file_size / (1024 * 1024), 2),
            "saved_at": datetime.now(UTC).isoformat(),
            "zip_info": zip_info,
        }

    async def _safe_remove_file(self, file_path: Path) -> None:
        """
        Безопасно удаляет файл, если он существует

        Args:
            file_path: Путь к файлу для удаления
        """
        try:
            # unlink() - это Path.remove(), но может блокировать I/O,
            # поэтому оборачиваем в to_thread для чистоты асинхронности
            await asyncio.to_thread(file_path.unlink)
            logger.debug(
                "Temporary file removed",
                extra={"path": str(file_path)},
            )
        except FileNotFoundError:
            # Файл уже отсутствует – ничего не делаем
            logger.debug(
                "File already removed, skipping",
                extra={"path": str(file_path)},
            )
        except OSError as e:
            logger.error(
                "Failed to remove temporary file",
                extra={"path": str(file_path), "error": str(e)},
            )


# ===== Фабрика для DI =====
def get_file_uploader() -> FileUploader:
    """
    Возвращает экземпляр FileUploader для внедрения зависимостей.
    """
    return FileUploader()
