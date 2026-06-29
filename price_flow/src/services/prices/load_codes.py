import asyncio
import shutil
import uuid

from pathlib import Path
from typing import Annotated, Any

import aiofiles.os as aios  # type: ignore[import-untyped]

from fastapi import Depends, UploadFile

from core.exceptions import (
    DatabaseAppError,
    DataProcessingError,
    ErrorMessages,
    FileAppNotFoundError,
    FileNotZipError,
    FileSizeError,
    FileUploadError,
    ZipExtractionError,
)
from core.logger import logger
from db.factory import AsyncDatabaseFactory
from interfaces.db.base import IDatabaseManager
from repositories.supplier_codes_repo import SupplierCodesRepo, get_supplier_codes_repo
from schemas.response_schemas import SuccessResponse
from services.file_uploader import FileUploader, get_file_uploader
from services.helpers import extract_zip


class LoaderCodes:

    def __init__(
        self,
        supplier_codes_repo: SupplierCodesRepo,
        file_uploader: FileUploader,
    ) -> None:
        self.supplier_codes_repo = supplier_codes_repo
        self.file_uploader = file_uploader
        self._db_manager: IDatabaseManager | None = None
        self._db_manager_lock = asyncio.Lock()

    async def _get_db_manager(self) -> IDatabaseManager:
        """
        Ленивая инициализация менеджера БД.

        Returns:
            Менеджер БД

        Raises:
            DatabaseError: Если не удалось инициализировать менеджер
        """
        if self._db_manager is None:
            async with self._db_manager_lock:
                if self._db_manager is None:  # Double-check locking
                    try:
                        self._db_manager = await AsyncDatabaseFactory.get_manager()
                        logger.debug("Менеджер БД успешно инициализирован")
                    except Exception as e:
                        logger.error(
                            "Ошибка инициализации менеджера БД",
                            extra={"error": str(e)},
                            exc_info=True,
                        )
                        raise DatabaseAppError(
                            message=(
                                "Не удалось инициализировать менеджер базы данных: "
                                f"{e!s}"
                            )
                        ) from e
        return self._db_manager

    async def cleanup(self) -> None:
        """Очистка ресурсов."""
        if self._db_manager:
            try:
                await self._db_manager.close()
                logger.debug("Менеджер БД закрыт")

            except asyncio.CancelledError:
                # Обработка отмены задачи
                logger.warning("Очистка ресурсов была отменена")
                raise  # Пробрасываем дальше для правильной обработки отмены

            except ConnectionError as e:
                # Ошибки соединения с БД
                logger.error(f"Ошибка соединения при закрытии менеджера БД: {e}")

            except TimeoutError as e:
                # Таймаут при закрытии соединения
                logger.warning(f"Таймаут при закрытии менеджера БД: {e}")

            except RuntimeError as e:
                # Ошибки выполнения (например, уже закрыто)
                if "closed" in str(e).lower() or "not connected" in str(e).lower():
                    logger.debug(f"Менеджер БД уже закрыт: {e}")
                else:
                    logger.error(f"Ошибка выполнения при закрытии менеджера БД: {e}")

            except AttributeError as e:
                # Если у менеджера нет метода close()
                logger.error(f"Менеджер БД не поддерживает метод close(): {e}")

            except Exception as e:  # noqa: BLE001
                # Обработка любых других неожиданных ошибок с логированием
                logger.error(
                    f"Неожиданная ошибка при очистке ресурсов: {e}", exc_info=True
                )

            finally:
                # Всегда сбрасываем ссылку на менеджер
                self._db_manager = None
                logger.debug("Ссылка на менеджер БД сброшена")

    async def load_file(self, file: UploadFile) -> SuccessResponse:
        """
        Орхестратор процесса:
        Загрузка -> Распаковка -> Парсинг -> Загрузка в БД -> Очистка.
        """
        zip_file_path: Path | None = None
        extract_dir: Path | None = None

        try:
            # 1. Загрузка ZIP файла
            upload_response = await self.file_uploader.upload_file(file)
            self._validate_upload_response(upload_response)
            zip_file_path = Path(upload_response.details["file_path"])  # type: ignore

            # 2. Подготовка директории для распаковки
            # Создаем временную папку с UUID, чтобы избежать конфликтов
            extract_subdir = f"{zip_file_path.stem}_extracted_{uuid.uuid4().hex[:8]}"
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
            db_result = await self.load_file_to_db(str(csv_file_path))

            return SuccessResponse(
                message="Данные успешно обработаны", details=db_result
            )

        except (
            FileNotZipError,
            FileSizeError,
            ZipExtractionError,
            FileUploadError,
            FileAppNotFoundError,
            DataProcessingError,
        ) as e:
            # Ошибки бизнес-логики, логируем warning и пробрасываем
            logger.warning(f"Ошибка обработки файла: {e}")
            raise

        except Exception as e:
            # Непредвиденные ошибки
            logger.exception(f"Критическая ошибка в load_file: {e}")
            error_message = "Внутренняя ошибка при обработке файла"
            raise RuntimeError(error_message) from e

        finally:
            # 6. Гарантированная очистка ресурсов
            if zip_file_path and zip_file_path.exists():
                await remove_file_async(zip_file_path)

            if extract_dir and extract_dir.exists():
                await remove_directory_async(extract_dir)

    def _validate_upload_response(self, upload_response: SuccessResponse) -> None:
        if not upload_response.details:
            error_message = "File not uploaded"
            raise FileUploadError(error_message)

    def _validate_file_found(self, files: list[Path]) -> None:
        if not files:
            raise DataProcessingError(ErrorMessages.ERR_MSG_CSV_NOT_FOUND)

    async def _unzip_file_async(self, zip_path: Path, extract_to: Path) -> None:
        """
        Запускает распаковку в отдельном потоке.
        """

        def _unzip_task() -> bool:
            return extract_zip(str(zip_path), str(extract_to))

        try:
            await asyncio.to_thread(_unzip_task)
            logger.info(f"Файл распакован в: {extract_to}")

        except (FileAppNotFoundError, ZipExtractionError):
            # Если это наши кастомные исключения — просто пробрасываем их выше
            raise

        except Exception as e:
            logger.error(
                f"Ошибка распаковки архива {zip_path.name}: {e}", exc_info=True
            )
            error_message = f"Ошибка при распаковке архива: {zip_path.name}"
            raise ZipExtractionError(zip_path, error_message) from e

    async def load_file_to_db(self, unpacked_file_path: str) -> dict[str, Any]:
        return await self.supplier_codes_repo.load_data(
            unpacked_file_path, "supplier_product_codes"
        )


async def remove_file_async(file_path: str | Path) -> bool:
    """
    Асинхронно удаляет файл.
    Возвращает True, если удаление прошло успешно.
    """
    path = Path(file_path)

    if not path.exists():
        logger.debug(f"Файл не найден, пропускаем удаление: {path}")
        return False

    try:
        await aios.remove(path)
        logger.info(f"Файл успешно удален: {path}")
    except OSError as e:
        logger.error(f"Ошибка при удалении файла {path}: {e}")
        return False
    else:
        return True


async def remove_directory_async(dir_path: str | Path) -> bool:
    """
    Рекурсивно удаляет директорию в отдельном потоке.
    """
    path = Path(dir_path)
    if not path.exists():
        return False

    def _rmdir_sync() -> None:
        shutil.rmtree(path)

    try:
        await asyncio.to_thread(_rmdir_sync)
        logger.info(f"Директория удалена: {path}")
    except OSError as e:
        logger.error(f"Ошибка удаления директории {path}: {e}")
        return False
    else:
        return True


def get_loader_codes(
    supplier_codes_repo: Annotated[SupplierCodesRepo, Depends(get_supplier_codes_repo)],
    file_uploader: Annotated[FileUploader, Depends(get_file_uploader)],
) -> LoaderCodes:
    return LoaderCodes(supplier_codes_repo, file_uploader)
