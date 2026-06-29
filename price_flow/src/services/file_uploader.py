import asyncio
import uuid
import zipfile

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiofiles  # type: ignore[import-untyped]

from fastapi import UploadFile

from core.exceptions import (
    ErrorMessages,
    FileNotZipError,
    FileSizeError,
    ZipExtractionError,
)
from core.logger import logger
from core.settings import settings
from schemas.response_schemas import SuccessResponse


UPLOAD_DIR = "uploads"  # Директория для загрузки файлов
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB максимальный размер файла


class FileUploader:

    def __init__(
        self,
        upload_dir: str | None = None,
        max_file_size: int | None = None,
    ):
        self.upload_dir = settings.BASE_DIR / Path(upload_dir or UPLOAD_DIR)
        self.max_file_size = int(max_file_size or MAX_FILE_SIZE)

        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def upload_file(
        self, file: UploadFile, save_subpath: str | None = None
    ) -> SuccessResponse:
        """
        Асинхронно загружает ZIP файл и сохраняет его локально

        Args:
            file: Загружаемый ZIP файл
            save_subpath: Опциональный подпуть для сохранения файла

        Returns:
            SuccessResponse с информацией о сохраненном файле

        Raises:
            FileNotZipError: Если файл не является ZIP архивом
            FileSizeError: Если размер файла превышает лимит
            ZipExtractionError: Если не удалось проверить ZIP архив
            Exception: При других ошибках сохранения файла
        """

        # Проверяем, что файл имеет расширение .zip
        self._validate_file_extension(file)
        save_dir = self._get_save_directory(save_subpath)

        original_name = file.filename or "unknown_upload.zip"

        logger.info(f"Начало загрузки файла: {original_name}")
        # Генерируем уникальное имя файла чтобы избежать перезаписи
        unique_filename = self._generate_unique_filename(original_name)
        file_path = save_dir / unique_filename

        try:
            # Асинхронно сохраняем файл с проверкой размера
            file_size = await self._save_file_with_size_check(
                file=file, file_path=file_path
            )

            # Проверяем валидность ZIP архива
            zip_info = await self._validate_zip_file(file_path)

            # Получаем информацию о файле
            file_info = self._build_file_info(
                original_filename=original_name,
                saved_filename=unique_filename,
                file_path=file_path,
                file_size=file_size,
                zip_info=zip_info,
            )

            logger.info(
                f"Файл успешно сохранен: {file_path} (Размер: {file_size} байт)"
            )

            return SuccessResponse(
                message="ZIP файл успешно сохранен", details=file_info
            )

        except (FileSizeError, ZipExtractionError, FileNotZipError) as e:
            # Ожидаемые ошибки бизнес-логики
            logger.warning(f"Ошибка валидации файла {original_name}: {e}")
            await self._safe_remove_file(file_path)
            raise
        except Exception as e:
            # Непредвиденные системные ошибки
            logger.exception(
                f"Критическая ошибка при сохранении файла {original_name}: {e}"
            )
            await self._safe_remove_file(file_path)
            # Создаем более конкретное исключение вместо голого Exception (TRY002)
            raise RuntimeError(ErrorMessages.ERR_MSG_SAVE_FAILED) from e

    def _validate_file_extension(self, file: UploadFile) -> None:
        """
        Проверяет, что файл имеет расширение .zip

        Args:
            file: Проверяемый файл

        Raises:
            FileNotZipError: Если файл не является ZIP архивом
        """
        if not file.filename or not file.filename.lower().endswith(".zip"):
            logger.warning(
                f"Попытка загрузки файла с неверным расширением: {file.filename}"
            )
            raise FileNotZipError(
                file.filename if file.filename else "empty_filename",
                ErrorMessages.ERR_MSG_NOT_ZIP,
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
            save_dir = self.upload_dir / safe_subpath
        else:
            save_dir = self.upload_dir

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
            FileSizeError: Если размер файла превышает лимит
        """
        file_size = 0
        chunk_size = 1024 * 1024  # 1MB

        try:
            async with aiofiles.open(file_path, "wb") as buffer:
                while chunk := await file.read(chunk_size):
                    file_size += len(chunk)

                    self._ensure_size_limit_not_exceeded(file_path, file_size)

                    await buffer.write(chunk)

        except FileSizeError:
            # Пробрасываем дальше, чтобы удалить файл в блоке выше
            raise
        except OSError as e:
            # Ошибки диска (нет места, права доступа)
            logger.error(f"Ошибка записи на диск: {e}")
            raise RuntimeError(ErrorMessages.ERR_MSG_SAVE_FAILED) from e

        return file_size

    def _ensure_size_limit_not_exceeded(
        self, file_path: Path, current_size: int
    ) -> None:
        """
        Проверяет размер файла. Выбрасывает исключение, если лимит превышен.
        Этот метод создан для соблюдения принципа 'Abstract raise to inner function'.
        """
        if current_size > self.max_file_size:
            limit_mb = self.max_file_size / (1024 * 1024)
            logger.warning(
                f"Превышен лимит размера файла: {current_size} > {self.max_file_size}"
            )
            error_message = f"{ErrorMessages.ERR_MSG_SIZE_LIMIT} ({limit_mb:.2f}MB)"
            raise FileSizeError(
                file_path, error_message, max_file_size=self.max_file_size
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
            with zipfile.ZipFile(file_path, "r") as zip_ref:
                file_list = zip_ref.namelist()
                return {
                    "total_files": len(file_list),
                    "files": file_list[:10],  # Ограничиваем вывод
                    "is_valid": True,
                    "compressed_size": file_path.stat().st_size,
                    "comment": (
                        zip_ref.comment.decode("utf-8", errors="ignore")
                        if zip_ref.comment
                        else None
                    ),
                }

        try:
            return await asyncio.to_thread(_extract_zip_info)

        except zipfile.BadZipFile as e:
            logger.warning(f"Невалидный ZIP архив: {file_path.name}")
            raise ZipExtractionError(
                file_path, ErrorMessages.ERR_MSG_INVALID_ZIP
            ) from e
        except OSError as e:
            # Например, файл был удален между сохранением и проверкой
            logger.error(f"Ошибка доступа к файлу при валидации: {e}")
            raise ZipExtractionError(
                file_path, ErrorMessages.ERR_MSG_VALIDATION_FAILED
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
        if file_path.exists():
            try:
                # unlink() - это Path.remove(), но может блокировать I/O,
                # поэтому оборачиваем в to_thread для чистоты асинхронности
                await asyncio.to_thread(file_path.unlink)
                logger.debug(f"Временный файл удален: {file_path}")
            except OSError as e:
                logger.error(f"Не удалось удалить файл {file_path}: {e}")


def get_file_uploader() -> FileUploader:
    return FileUploader()
