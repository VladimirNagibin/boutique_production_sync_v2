import asyncio
import uuid

from pathlib import Path
from typing import Annotated

from fastapi import Depends, UploadFile

from common.exceptions.app_exceptions import DataProcessingError
from common.exceptions.database import DatabaseLoadError
from common.exceptions.enums import ErrorMessages
from common.exceptions.file import (
    CsvParsingError,
    FileAppNotFoundError,
    FileTooLargeError,
    FileUploadError,
    ZipExtractionError,
)
from core.logger import get_logger
from repositories.supplier_clothing_codes_repo import (
    SupplierClothingCodeRepository,
    get_supplier_clothing_codes_repo,
)
from schemas.response_schemas import SuccessResponse
from services.file_uploader import FileUploader, get_file_uploader
from services.helpers import extract_zip
from services.prices.load_codes import (
    remove_directory_async,
    remove_file_async,
)


logger = get_logger(__name__)


class LoaderClothingCodes:
    """Оркестратор загрузки CSV кодов одежды в PostgreSQL."""

    def __init__(
        self,
        clothing_codes_repo: SupplierClothingCodeRepository,
        file_uploader: FileUploader,
    ) -> None:
        self.clothing_codes_repo = clothing_codes_repo
        self.file_uploader = file_uploader

    async def load_file(self, file: UploadFile) -> SuccessResponse:
        """
        Загружает CSV или ZIP с CSV, заменяет таблицу
        и удаляет временные файлы.

        Args:
            file: Загружаемый CSV или ZIP.

        Returns:
            SuccessResponse со статистикой загрузки.
        """
        uploaded_path: Path | None = None
        extract_dir: Path | None = None

        try:
            logger.info(
                "Starting clothing codes import",
                extra={"file_name": file.filename},
            )
            upload_response = await self.file_uploader.upload_csv_or_zip(file)
            self._validate_upload_response(upload_response)
            details = upload_response.details
            assert details is not None
            uploaded_path = Path(details["file_path"])
            csv_file_path, extract_dir = await self._resolve_csv_path(
                uploaded_path
            )
            db_result = (
                await self.clothing_codes_repo.load_from_csv_with_truncate(
                    str(csv_file_path)
                )
            )
            logger.info(
                "Clothing codes import completed",
                extra={
                    "source_file_name": csv_file_path.name,
                    "rows_loaded": db_result.get("rows_loaded"),
                },
            )
            return SuccessResponse(
                message="Clothing codes successfully processed",
                details=db_result,
            )
        except (
            FileTooLargeError,
            FileUploadError,
            ZipExtractionError,
            FileAppNotFoundError,
            CsvParsingError,
            DatabaseLoadError,
            DataProcessingError,
        ) as e:
            logger.warning(
                "Clothing codes file processing error",
                extra={"error": str(e), "error_type": type(e).__name__},
            )
            raise
        except Exception as e:
            logger.error(
                "Unexpected error during clothing codes import",
                extra={"error": str(e)},
                exc_info=True,
            )
            error_message = "Внутренняя ошибка при обработке файла"
            raise DataProcessingError(error_message) from e
        finally:
            if uploaded_path and uploaded_path.exists():
                await remove_file_async(uploaded_path)
            if extract_dir and extract_dir.exists():
                await remove_directory_async(extract_dir)

    async def _resolve_csv_path(
        self, uploaded_path: Path
    ) -> tuple[Path, Path | None]:
        """
        Возвращает путь к CSV: сам файл или распакованный из ZIP.

        Args:
            uploaded_path: Путь к загруженному файлу.

        Returns:
            Кортеж (путь к CSV, директория распаковки или None).
        """
        if uploaded_path.suffix.lower() != ".zip":
            return uploaded_path, None

        extract_dir = (
            uploaded_path.parent
            / f"{uploaded_path.stem}_extracted_{uuid.uuid4().hex[:8]}"
        )
        extract_dir.mkdir(exist_ok=True)
        await self._unzip_file_async(uploaded_path, extract_dir)
        csv_files = list(extract_dir.glob("*.csv"))
        if not csv_files:
            self._raise_csv_not_found()
        return csv_files[0], extract_dir

    def _validate_upload_response(
        self, upload_response: SuccessResponse
    ) -> None:
        """Проверяет, что загрузчик вернул путь к файлу."""
        if (
            not upload_response.details
            or "file_path" not in upload_response.details
        ):
            self._raise_missing_file_path()

    @staticmethod
    def _raise_csv_not_found() -> None:
        """Бросает ошибку, если в архиве нет CSV."""
        raise DataProcessingError(ErrorMessages.CSV_NOT_FOUND.message)

    @staticmethod
    def _raise_missing_file_path() -> None:
        """Бросает ошибку, если загрузчик не вернул путь к файлу."""
        error_message = "Upload response missing 'file_path'"
        unknown_path = "unknown"
        raise FileUploadError(unknown_path, error_message)

    async def _unzip_file_async(
        self, zip_path: Path, extract_to: Path
    ) -> None:
        """Распаковывает ZIP в отдельном потоке."""

        def _unzip_task() -> None:
            extract_zip(str(zip_path), str(extract_to))

        try:
            await asyncio.to_thread(_unzip_task)
        except (FileAppNotFoundError, ZipExtractionError):
            raise
        except Exception as e:
            logger.error(
                "Failed to unzip clothing codes archive",
                extra={"zip_path": str(zip_path), "error": str(e)},
                exc_info=True,
            )
            raise ZipExtractionError(
                zip_path,
                f"Error extracting archive: {zip_path.name}",
            ) from e


def get_loader_clothing_codes(
    clothing_codes_repo: Annotated[
        SupplierClothingCodeRepository,
        Depends(get_supplier_clothing_codes_repo),
    ],
    file_uploader: Annotated[FileUploader, Depends(get_file_uploader)],
) -> LoaderClothingCodes:
    """Фабрика оркестратора загрузки кодов одежды."""
    return LoaderClothingCodes(clothing_codes_repo, file_uploader)
