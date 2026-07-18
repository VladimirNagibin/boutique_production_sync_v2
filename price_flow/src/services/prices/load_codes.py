import asyncio
import shutil
import uuid

from pathlib import Path
from typing import Annotated, Any, cast

import aiofiles.os as aios

from fastapi import Depends, UploadFile

from common.exceptions.app_exceptions import DataProcessingError
from common.exceptions.enums import ErrorMessages
from common.exceptions.file import (
    FileAppNotFoundError,
    FileNotZipError,
    FileTooLargeError,
    FileUploadError,
    ZipExtractionError,
)
from common.logger import logger

# from repositories.supplier_codes_repo import (
#     SupplierCodesRepo,
#     get_supplier_codes_repo,
# )
from repositories.supplier_product_codes_repo import (
    SupplierProductCodeRepository,
    get_supplier_product_codes_repo,
)
from schemas.response_schemas import SuccessResponse
from services.file_uploader import FileUploader, get_file_uploader
from services.helpers import extract_zip


class LoaderCodes:
    """
    Оркестратор загрузки и обработки файлов с кодами поставщиков.
    """

    def __init__(
        self,
        supplier_codes_repo: SupplierProductCodeRepository,
        file_uploader: FileUploader,
    ) -> None:
        self.supplier_codes_repo = supplier_codes_repo
        self.file_uploader = file_uploader

    async def load_file(self, file: UploadFile) -> SuccessResponse:
        """
        Оркестрирует процесс:
        загрузка -> распаковка -> парсинг -> загрузка в БД -> очистка.

        Args:
            file: Загружаемый ZIP-файл.

        Returns:
            SuccessResponse с деталями результата.

        Raises:
            FileNotZipError, FileTooLargeError, ZipExtractionError,
            FileUploadError, FileAppNotFoundError, DataProcessingError.
        """
        zip_file_path: Path | None = None
        extract_dir: Path | None = None

        try:
            # 1. Загрузка ZIP файла
            upload_response = await self.file_uploader.upload_file(file)
            self._validate_upload_response(upload_response)
            zip_file_path = Path(upload_response.details["file_path"])

            # 2. Подготовка директории для распаковки
            # Создаем временную папку с UUID, чтобы избежать конфликтов
            extract_subdir = (
                f"{zip_file_path.stem}_extracted_{uuid.uuid4().hex[:8]}"
            )
            extract_dir = zip_file_path.parent / extract_subdir
            extract_dir.mkdir(exist_ok=True)

            # 3. Асинхронная распаковка
            await self._unzip_file_async(zip_file_path, extract_dir)

            # 4. Поиск CSV файла
            csv_files = list(extract_dir.glob("*.csv"))
            txt_files = list(extract_dir.glob("*.txt"))
            all_files = csv_files + txt_files
            self._validate_file_found(all_files)

            # Берем первый найденный CSV
            csv_file_path = all_files[0]

            # 5. Загрузка в БД
            db_result = (
                await self.supplier_codes_repo.load_from_csv_with_truncate(
                    str(csv_file_path)
                )
            )

            return SuccessResponse(
                message="Data successfully processed", details=db_result
            )

        except (
            FileNotZipError,
            FileTooLargeError,
            ZipExtractionError,
            FileUploadError,
            FileAppNotFoundError,
            DataProcessingError,
        ) as e:
            # Ошибки бизнес-логики, логируем warning и пробрасываем
            logger.warning(
                "File processing error",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            raise

        except Exception as e:
            # Непредвиденные ошибки
            logger.error(
                "Unexpected error during file processing",
                extra={"error": str(e)},
                exc_info=True,
            )
            error_message = "Внутренняя ошибка при обработке файла"
            raise DataProcessingError(error_message) from e

        finally:
            # 6. Гарантированная очистка ресурсов
            if zip_file_path and zip_file_path.exists():
                await remove_file_async(zip_file_path)

            if extract_dir and extract_dir.exists():
                await remove_directory_async(extract_dir)

    def _validate_upload_response(
        self, upload_response: SuccessResponse
    ) -> None:
        """
        Проверяет ответ от загрузчика файлов.

        Args:
            upload_response: Ответ после загрузки.

        Raises:
            FileUploadError: Если ответ не содержит путь к файлу.
        """
        if (
            not upload_response.details
            or "file_path" not in upload_response.details
        ):
            error_message = "Upload response missing 'file_path'"
            raise FileUploadError(error_message)

    def _validate_file_found(self, files: list[Path]) -> None:
        """
        Проверяет, что найден хотя бы один CSV/TXT файл.

        Args:
            files: Список найденных файлов.

        Raises:
            DataProcessingError: Если список пуст.
        """
        if not files:
            raise DataProcessingError(ErrorMessages.CSV_NOT_FOUND.message)

    async def _unzip_file_async(
        self, zip_path: Path, extract_to: Path
    ) -> None:
        """
        Распаковывает архив в отдельном потоке.

        Args:
            zip_path: Путь к ZIP-файлу.
            extract_to: Директория для распаковки.

        Raises:
            ZipExtractionError: При ошибках распаковки.
        """

        def _unzip_task() -> None:
            extract_zip(str(zip_path), str(extract_to))

        try:
            await asyncio.to_thread(_unzip_task)
            logger.info(
                "Archive unzipped",
                extra={
                    "zip_path": str(zip_path),
                    "extract_to": str(extract_to),
                },
            )
        except (FileAppNotFoundError, ZipExtractionError):
            # Пробрасываем кастомные исключения без изменений
            raise

        except Exception as e:
            logger.error(
                "Failed to unzip archive",
                extra={"zip_path": str(zip_path), "error": str(e)},
                exc_info=True,
            )
            raise ZipExtractionError(
                zip_path,
                f"Error extracting archive: {zip_path.name}",
            ) from e

    async def load_file_to_db(
        self, unpacked_file_path: str
    ) -> dict[str, Any]:
        """
        Загружает данные из CSV-файла в таблицу БД.

        Args:
            unpacked_file_path: Путь к распакованному CSV-файлу.

        Returns:
            Результат загрузки в виде словаря.
        """
        result = await self.supplier_codes_repo.load_data(
            unpacked_file_path, "supplier_product_codes"
        )
        return cast("dict[str, Any]", result)


# ===== Вспомогательные асинхронные функции для работы с фс =====


async def remove_file_async(file_path: str | Path) -> bool:
    """
    Асинхронно удаляет файл.

    Args:
        file_path: Путь к файлу.

    Returns:
        True, если удаление успешно; False, если файл не найден или ошибка.
    """
    path = Path(file_path)

    try:
        await aios.remove(path)
        logger.info("File removed", extra={"path": str(path)})
    except FileNotFoundError:
        logger.debug(
            "File not found, skipping removal", extra={"path": str(path)}
        )
        return False
    except OSError as e:
        logger.error(
            "Failed to remove file",
            extra={"path": str(path), "error": str(e)},
        )
        return False
    else:
        return True


async def remove_directory_async(dir_path: str | Path) -> bool:
    """
    Рекурсивно удаляет директорию в отдельном потоке.

    Args:
        dir_path: Путь к директории.

    Returns:
        True, если удаление успешно; False, если директория не найдена или
        ошибка.
    """
    path = Path(dir_path)

    def _rmdir_sync() -> None:
        shutil.rmtree(path)

    try:
        await asyncio.to_thread(_rmdir_sync)
        logger.info("Directory removed", extra={"path": str(path)})
    except FileNotFoundError:
        logger.debug(
            "Directory not found, skipping removal", extra={"path": str(path)}
        )
        return False
    except OSError as e:
        logger.error(
            "Failed to remove directory",
            extra={"path": str(path), "error": str(e)},
        )
        return False
    else:
        return True


# ===== Фабрика для DI =====


def get_loader_codes(
    supplier_codes_repo: Annotated[
        SupplierProductCodeRepository,
        Depends(get_supplier_product_codes_repo),
    ],
    file_uploader: Annotated[FileUploader, Depends(get_file_uploader)],
) -> LoaderCodes:
    """
    Фабрика для создания экземпляра LoaderCodes.
    """
    return LoaderCodes(supplier_codes_repo, file_uploader)
