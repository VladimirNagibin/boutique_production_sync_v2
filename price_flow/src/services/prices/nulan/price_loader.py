import asyncio
import datetime
import shutil
import uuid

from datetime import UTC
from pathlib import Path
from typing import Annotated, Any, ClassVar, cast

import aiofiles.os as aios
import numpy as np
import pandas as pd
import requests


# import xlrd
from fastapi import Depends, UploadFile
from pandas import DataFrame

from core.exceptions.app_exceptions import (
    ApiError,
    DataProcessingError,
    DownloadError,
    ErrorMessages,
)
from core.exceptions.file import (
    FileAppNotFoundError,
    FileUploadError,
    ZipExtractionError,
)
from core.logger import logger
from core.settings import settings
from repositories.supplier_clothing_repo import (
    SupplierClothingRepo,
    get_supplier_codes_repo,
)
from schemas.converter_schemas import UploadResult
from schemas.response_schemas import SuccessResponse
from schemas.supplier_schemas import SupplierProductPrice
from services.converter import FileUploader as Converter
from services.converter import get_file_uploader as get_converter
from services.file_uploader import FileUploader, get_file_uploader
from services.helpers import extract_zip

from .config import (
    FILE_CHANGE,
    FILENAME_MAPPING,
    FOLDER_NAME,
    PRODUCT_COLOR_COLUMN,
    PRODUCT_NAME_COLUMN,
    PRODUCT_PRICE_COLUMN,
    PRODUCT_SIGN_COLUMN,
    PRODUCT_SIZE_RANGE,
    PRODUCT_SKIP_HEAD_ROWS,
    PRODUCT_START_REMAINS_COLUMN,
    TEMP_FOLDER_NAME,
)


FOLDER = "uploads/"


class PriceLoader:
    """Сервис для загрузки и обработки прайс-листов из облачного хранилища."""

    DEFAULT_SUPPLIER_ID: ClassVar[int] = 564

    def __init__(
        self,
        supplier_clothing_repo: SupplierClothingRepo,
        file_uploader: FileUploader,
        converter: Converter,
        base_dir: Path | None = None,
        supplier_id: int = DEFAULT_SUPPLIER_ID,
    ) -> None:
        self.supplier_clothing_repo = supplier_clothing_repo
        self.file_uploader = file_uploader
        self.converter = converter
        self.base_dir = base_dir or settings.app.base_dir
        self.api_url = settings.price.nulan_api_url
        self.public_key = settings.price.nulan_price_url
        self.supplier_id = supplier_id

        # Определяем папку для временных файлов
        self.temp_dir = (
            self.base_dir / Path(FOLDER_NAME) / Path(TEMP_FOLDER_NAME)
        )
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def process_price(self) -> DataFrame:
        """
        Основной метод запуска синхронизации файлов.
        """
        # await self.supplier_clothing_repo.get_supplier_category_by_code(
        #     self.supplier_id, 100029
        # )
        try:
            logger.info("Запуск синхронизации прайс-листов")
            await self._fetch_and_process_directory(self.public_key)
            await self._parse_files()
            # price_as_is = self.temp_dir / "price_as_is.xlsx"
            df = self.supplier_clothing_repo.save_price_as_is()
        except Exception as e:
            logger.error(
                "Критическая ошибка при синхронизации", exc_info=True
            )
            error_code = "PROCESS_PRICE_ERROR"
            raise DownloadError(
                error_code, f"Сбой синхронизации: {e!s}"
            ) from e
        else:
            return df

    async def _fetch_and_process_directory(self, public_url: str) -> None:
        """
        Асинхронная обертка для получения содержимого папки.
        """
        items = await asyncio.to_thread(
            self._fetch_directory_content_sync, public_url
        )
        await self._process_directory_items(items)

    def _fetch_directory_content_sync(
        self, public_url: str
    ) -> list[dict[str, Any]]:
        """
        Синхронный метод: получает метаданные папки через API и запускает
        обработку элементов.
        """
        params: dict[str, Any] = {"public_key": public_url, "limit": 1000}
        error_code = "API_STRUCTURE_ERROR"
        try:
            response = requests.get(self.api_url, params=params, timeout=1000)
            if response.status_code != 200:
                error_message = (
                    f"Ошибка доступа к API: {response.status_code}"
                )
                raise ApiError(error_message)

            data: dict[str, Any] = response.json()

            # Проверяем структуру, чтобы избежать KeyError
            embedded = data.get("_embedded")
            if not isinstance(embedded, dict):
                raise ApiError(
                    error_code, "Некорректный ответ API (ожидается _embedded)"
                )

            items = embedded.get("items", [])
            if not isinstance(items, list):
                raise ApiError(
                    error_code,
                    "Некорректный ответ API (ожидается список items)",
                )

            # Приводим к нужному типу (для mypy)
            # return cast("list[dict[str, Any]]", items)

            # items = data.get("_embedded", {}).get("items", [])

        except requests.RequestException as e:
            error_message = f"Ошибка запроса к API: {e!s}"
            raise ApiError(error_message) from e
        except KeyError as e:
            logger.error(f"Ошибка структуры ответа API: {e}")
            raise ApiError(error_code, "Некорректный ответ API") from e
        else:
            return cast("list[dict[str, Any]]", items)

    async def _process_directory_items(
        self, items: list[dict[str, Any]]
    ) -> None:
        """
        Обрабатывает список элементов (файлов и папок), полученных из API.
        """
        for item in items:
            item_name = item.get("name")
            item_type = item.get("type")
            item_name = str(item_name) or f"{uuid.uuid4()!s}.xlsx"

            if item_type == "file":
                file_url = item.get("file")
                if file_url:
                    await self._download_file(file_url, item_name)
            elif item_type == "dir":
                subfolder_url = item.get("public_url")
                if subfolder_url:
                    # Рекурсивная загрузка поддиректорий
                    await self._fetch_and_process_directory(subfolder_url)

    async def _download_file(self, url: str, filename: str) -> None:
        """
        Асинхронная обертка для скачивания файла.
        """
        try:
            await asyncio.to_thread(self._download_file_sync, url, filename)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Error load {filename}: {url} {e}")

    def _download_file_sync(self, url: str, original_filename: str) -> None:
        """
        Синхронный метод: скачивает файл и сохраняет его под каноническим
        именем.
        """
        # 1. Определяем каноническое имя файла по маппингу
        # Если имени нет в маппинге, оставляем оригинальное
        target_filename = FILENAME_MAPPING.get(
            original_filename, original_filename
        )
        save_path: Path = self.temp_dir / target_filename
        # 2. Выполняем запрос с обработкой исключений
        try:
            logger.debug(f"Загрузка файла: {target_filename} из {url}")

            # 2. Скачивание
            response = requests.get(url, stream=True, timeout=1000)
            response.raise_for_status()
        except requests.RequestException as e:
            error_msg = f"Request failed for {target_filename}: {e}"
            logger.error(error_msg)
            error_code = (
                f"DOWNLOAD_FAILED status code: {response.status_code}"
            )
            raise DownloadError(
                error_code, error_msg, details={"url": url}
            ) from e
        # 2. Сохраняем файл (используем Path.open())
        try:
            with save_path.open("wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
        except OSError as e:
            error_msg = f"File write error for {original_filename}"
            logger.error(error_msg, exc_info=True)
            error_code = "FILE_WRITE_ERROR"
            raise DownloadError(error_code, error_msg) from e
        except Exception as e:
            # Ловим всё остальное, но логируем и пробрасываем
            logger.error(f"Unexpected error: {e}", exc_info=True)
            raise

        logger.info(f"File successfully saved: {save_path}")

    async def _parse_files(self) -> None:
        code_max = await self.supplier_clothing_repo.get_max_code_async(
            self.supplier_id
        )
        current_code = code_max + 1
        await self.supplier_clothing_repo.clear_supplier_price(
            self.supplier_id
        )
        for _, file in FILENAME_MAPPING.items():
            await self._parse_file(self.temp_dir / file, current_code)
            # break

    async def _parse_file(self, file: str | Path, current_code: int) -> None:
        print(datetime.datetime.now(UTC).time())
        print(f"----------- {file} ---------------")
        repo = self.supplier_clothing_repo
        inf = pd.read_excel(file, skiprows=PRODUCT_SKIP_HEAD_ROWS)
        sizes: list[str] = []
        product_name = ""
        product_price = 0
        price_supplier: list[SupplierProductPrice] = []
        for s in inf.itertuples():
            if not np.isnan(s[PRODUCT_SIGN_COLUMN]):
                product_name = s[PRODUCT_NAME_COLUMN]
                if file == self.temp_dir / FILE_CHANGE:
                    product_name = product_name.replace("cont", "Conte")
                product_price = s[PRODUCT_PRICE_COLUMN]
                product_price = (
                    0 if np.isnan(product_price) else product_price
                )
                sizes.clear()
                for i in PRODUCT_SIZE_RANGE:
                    size = s[i]
                    if isinstance(size, str):
                        sizes.append(size)
            else:
                if product_price > 0:
                    product_color = s[PRODUCT_COLOR_COLUMN]
                    for i, size in enumerate(sizes):
                        remains = s[i + PRODUCT_START_REMAINS_COLUMN]
                        if isinstance(remains, str):
                            supplier_product = (
                                await repo.get_supplier_product(
                                    self.supplier_id,
                                    product_name,
                                    size,
                                    product_color,
                                )
                            )
                            if supplier_product:
                                code = supplier_product.code
                                brand = supplier_product.category
                                subgroup = supplier_product.subcategory
                                brands = (
                                    await repo.get_supplier_category_by_code(
                                        self.supplier_id, code
                                    )
                                )
                                if brands:
                                    brand = brands.category
                                    subgroup = brands.subcategory
                            else:
                                code, brand, subgroup = current_code, "?", "?"
                                current_code += 1

                            supplier_product_price = SupplierProductPrice(
                                code=code,
                                name=f"{product_name} {size} {product_color}",
                                category=brand,
                                subcategory=subgroup,
                                supplier_id=self.supplier_id,
                                product_summary=product_name,
                                size=size,
                                color=product_color,
                                price=product_price,
                            )
                            price_supplier.append(supplier_product_price)

        await repo.add_supplier_price(price_supplier)
        # return current_code

    async def load_products(self, file: UploadFile) -> UploadResult:
        """
        Орхестратор процесса:
        Загрузка -> Распаковка -> Загрузка в БД -> Очистка.
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

            # 4. Поиск XLSX файла
            xlsx_files = list(extract_dir.glob("*.xlsx"))
            xls_files = list(extract_dir.glob("*.xls"))
            all_files = xlsx_files + xls_files
            self._validate_file_found(all_files)

            # Берем первый найденный CSV
            xlsx_file_path = all_files[0]

            # 5. Загрузка в БД
            await self.load_file_to_db(str(xlsx_file_path))

            # 6
            price_filename = self.temp_dir / Path("price.xlsx")
            self.save_price_for_load(price_filename)

            # 7. Конвертация
            logger.info("Конвертация Excel файла...")
            upload_result = self.converter.upload_file(price_filename)
        except (
            # FileSizeError,
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
        else:
            return upload_result
        finally:
            # 6. Гарантированная очистка ресурсов
            if zip_file_path and zip_file_path.exists():
                await remove_file_async(zip_file_path)

            if extract_dir and extract_dir.exists():
                await remove_directory_async(extract_dir)

    def _validate_upload_response(
        self, upload_response: SuccessResponse
    ) -> None:
        if not upload_response.details:
            error_message = "File not uploaded"
            raise FileUploadError(error_message)

    async def _unzip_file_async(
        self, zip_path: Path, extract_to: Path
    ) -> None:
        """
        Запускает распаковку в отдельном потоке.
        """

        def _unzip_task() -> None:
            extract_zip(str(zip_path), str(extract_to))

        try:
            await asyncio.to_thread(_unzip_task)
            logger.info(f"Файл распакован в: {extract_to}")

        except (FileAppNotFoundError, ZipExtractionError):
            # Если это наши кастомные исключения — просто пробрасываем их выше
            raise

        except Exception as e:
            logger.error(
                f"Ошибка распаковки архива {zip_path.name}: {e}",
                exc_info=True,
            )
            error_message = f"Ошибка при распаковке архива: {zip_path.name}"
            raise ZipExtractionError(zip_path, error_message) from e

    def _validate_file_found(self, files: list[Path]) -> None:
        if not files:
            raise DataProcessingError(ErrorMessages.ERR_MSG_CSV_NOT_FOUND)

    async def load_file_to_db(self, unpacked_file_path: str) -> None:
        await self.supplier_clothing_repo.load_data(
            unpacked_file_path, "supplier_price"
        )

    def save_price_for_load(self, file_name: str | Path) -> None:
        data_frame = self.supplier_clothing_repo.save_price_for_load()
        excel_file_path = file_name
        brand = ""
        subgroup = ""
        price_all = []
        price_all.append(["", "", ""])
        for s in data_frame.itertuples():
            brand_current = s.category
            subgroup_current = s.subcategory
            code = s.code
            name = s.name
            price = s.price
            if brand != brand_current:
                brand = brand_current
                # print(f'{brand} =================')
                price_all.append(["", brand, ""])
            if subgroup != subgroup_current:
                subgroup = subgroup_current
                price_all.append(["", subgroup, ""])
                # print(f'{subgroup} ---------------')
            # print(code, name, price)
            price_all.append([code, name, price])
        df = pd.DataFrame(price_all, columns=["code", "name", "price"])
        df.to_excel(excel_file_path, index=False)

    async def upd_table(self) -> None:
        await self.supplier_clothing_repo.fix_supplier_id_type()


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


# Dependency для FastAPI
def get_price_loader(
    # settings: Annotated[Any, Depends(lambda: settings)],
    supplier_clothing_repo: Annotated[
        SupplierClothingRepo, Depends(get_supplier_codes_repo)
    ],
    file_uploader: Annotated[FileUploader, Depends(get_file_uploader)],
    converter: Annotated[Converter, Depends(get_converter)],
    # file_uploader: Annotated[FileUploader, Depends(get_file_uploader)],
    # supplier_id: int = PriceLoader.DEFAULT_SUPPLIER_ID,
) -> PriceLoader:
    """
    Dependency для получения экземпляра PriceLoader.

    Args:
        settings: Настройки приложения
        supplier_codes_repo: Репозиторий данных поставщика
        supplier_id: ID поставщика

    Returns:
        PriceLoader: Экземпляр сервиса
    """
    return PriceLoader(
        # settings=settings,
        supplier_clothing_repo=supplier_clothing_repo,
        file_uploader=file_uploader,
        converter=converter,
        # supplier_id=supplier_id,
    )
