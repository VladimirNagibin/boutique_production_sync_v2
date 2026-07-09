from __future__ import annotations

import time

from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import pandas as pd

from fastapi import Depends
from sqlalchemy import delete, select, text, update

from core.exceptions.database import DatabaseLoadError
from core.exceptions.file import CsvParsingError, FileAppNotFoundError
from core.logger import logger
from db.postgres import get_session_generator, run_sync_db_operation
from models.supplier_models import SupplierProductCode


if TYPE_CHECKING:
    from pandas import DataFrame
    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncSession


# ===== Константы =====
DEFAULT_CHUNKSIZE: int = 10000
COMMON_ENCODINGS: tuple[str, ...] = (
    "utf-8",
    "cp1251",
    "windows-1251",
    "iso-8859-1",
)


class SupplierProductCodeRepository:
    """
    Репозиторий для работы с таблицей supplier_product_codes (SQLAlchemy ORM).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ----- Публичные CRUD-методы -----

    async def get_all(
        self,
        supplier_id: int | None = None,
        skip: int = 0,
        limit: int = 1000,
    ) -> list[SupplierProductCode]:
        """Возвращает список записей с фильтрацией по поставщику."""
        stmt = select(SupplierProductCode)
        if supplier_id is not None:
            stmt = stmt.where(SupplierProductCode.supplier_id == supplier_id)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id(self, record_id: int) -> SupplierProductCode | None:
        """Возвращает запись по ID."""
        result = await self._session.execute(
            select(SupplierProductCode).where(
                SupplierProductCode.id == record_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_supplier_code(
        self, supplier_id: int, code: int
    ) -> SupplierProductCode | None:
        """Возвращает запись по supplier_id и code."""
        stmt = select(SupplierProductCode).where(
            SupplierProductCode.supplier_id == supplier_id,
            SupplierProductCode.code == code,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, data: dict[str, Any]) -> SupplierProductCode:
        """Создаёт новую запись."""
        instance = SupplierProductCode(**data)
        self._session.add(instance)
        await self._session.flush()
        return instance

    async def update(
        self, record_id: int, data: dict[str, Any]
    ) -> SupplierProductCode | None:
        """Обновляет запись и возвращает обновлённый объект."""
        stmt = (
            update(SupplierProductCode)
            .where(SupplierProductCode.id == record_id)
            .values(**data)
            .returning(SupplierProductCode)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def delete(self, record_id: int) -> bool:
        """Удаляет запись, возвращает True если удаление произошло."""
        stmt = delete(SupplierProductCode).where(
            SupplierProductCode.id == record_id
        )
        result = await self._session.execute(stmt)
        return bool(result.rowcount > 0)  # type: ignore[attr-defined]

    # ----- Массовая загрузка из CSV (синхронная, через pandas) -----

    async def load_from_csv_with_truncate(
        self,
        csv_path: str | Path,
        chunksize: int = DEFAULT_CHUNKSIZE,
    ) -> dict[str, Any]:
        """
        Очищает таблицу и загружает данные из CSV-файла.

        Args:
            csv_path: Путь к CSV-файлу с разделителем ';' и кавычками.
            chunksize: Размер пакета для вставки.

        Returns:
            Словарь со статистикой загрузки.

        Raises:
            FileAppNotFoundError: Если файл не найден.
            DatabaseLoadError: При ошибках загрузки.
            CsvParsingError: При ошибках парсинга CSV.
        """
        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileAppNotFoundError(
                csv_path, f"CSV file not found: {csv_path}"
            )
        logger.info(
            "Starting CSV load with truncate",
            extra={"file": str(csv_path), "chunksize": chunksize},
        )
        start_time = time.time()

        def _sync_load(sync_engine: Engine) -> dict[str, Any]:
            """
            Синхронная загрузка: читает CSV, выполняет TRUNCATE и вставку.
            """
            # 1. Чтение и валидация CSV
            df = self._read_csv_file(csv_path)

            # 2. Загрузка в БД
            rows_loaded = self._load_dataframe_to_db(
                df, sync_engine, chunksize
            )

            processing_time = int((time.time() - start_time) * 1000)
            return {
                "status": "success",
                "rows_loaded": rows_loaded,
                "processing_time_ms": processing_time,
                "file_path": str(csv_path),
                "file_size_bytes": csv_path.stat().st_size,
                "chunksize": chunksize,
            }

        try:
            # Запускаем синхронную функцию в отдельном потоке
            result = await run_sync_db_operation(_sync_load)
            logger.info(
                "CSV data loaded with truncate",
                extra={
                    "table": "supplier_product_codes",
                    "rows": result["rows_loaded"],
                    "time_ms": result["processing_time_ms"],
                    "file": str(csv_path),
                },
            )
        except (CsvParsingError, FileAppNotFoundError, DatabaseLoadError):
            # Эти ошибки логируются внутри методов, пробрасываем дальше
            raise
        except Exception as e:
            logger.error(
                "Failed to load CSV with truncate",
                extra={"error": str(e), "file": str(csv_path)},
                exc_info=True,
            )
            error_message = f"Error loading CSV: {e}"
            raise DatabaseLoadError(error_message) from e
        else:
            return result  # type: ignore[no-any-return]

    # ----- Приватные вспомогательные методы -----

    def _read_csv_file(self, csv_path: Path) -> DataFrame:
        """
        Читает CSV файл с обработкой ошибок и логированием.

        Args:
            csv_path: Путь к CSV файлу

        Returns:
            DataFrame: Прочитанные данные

        Raises:
            CsvParsingError: При любых ошибках чтения или парсинга.
        """
        logger.debug("Reading CSV file", extra={"path": str(csv_path)})
        encoding = self._detect_file_encoding(csv_path)
        logger.debug(
            f"Определена кодировка файла: {encoding}",
            extra={"file_path": str(csv_path)},
        )
        try:
            # Читаем файл с обработкой ошибок
            df = pd.read_csv(
                csv_path,
                sep=";",
                escapechar="\\",
                encoding=encoding,
                on_bad_lines="warn",  # Предупреждаем о проблемных строках
                dtype=str,  # Читаем все как строки для гибкости
                low_memory=False,  # Для больших файлов
                quotechar='"',
                doublequote=True,
                skipinitialspace=True,
                na_filter=False,  # Не фильтровать NaN для производительности
            )
        except UnicodeDecodeError as e:
            logger.error(f"Ошибка кодировки: {e}", exc_info=True)
            raise CsvParsingError(
                csv_path,
                f"Не удалось прочитать файл из-за кодировки: {csv_path}",
            ) from e

        except pd.errors.EmptyDataError as e:
            logger.warning(f"CSV файл пуст или поврежден: {csv_path}")
            raise CsvParsingError(
                csv_path, "Файл пуст или содержит только заголовки."
            ) from e

        except pd.errors.ParserError as e:
            logger.error(f"Ошибка парсинга CSV: {e}", exc_info=True)
            raise CsvParsingError(
                csv_path, f"Формат файла не соответствует CSV: {e}"
            ) from e

        except Exception as e:
            # Ловим остальные возможные ошибки pandas
            logger.error(
                f"Неожиданная ошибка при чтении CSV: {e}", exc_info=True
            )
            raise CsvParsingError(
                csv_path, f"Ошибка при чтении файла: {e}"
            ) from e

        # Логируем информацию о прочитанных данных
        logger.info(
            "CSV file read",
            extra={
                "path": str(csv_path),
                "rows": len(df),
                "columns": len(df.columns),
                "encoding": encoding,
            },
        )

        # Проверяем наличие данных
        self._validate_data_frame(df, csv_path)

        # Очищаем имена колонок
        df.columns = df.columns.str.strip().str.lower()

        # Проверяем необходимые колонки
        required_columns = [
            "id",
            "code",
            "name",
            "category",
            "subcategory",
            "supplier_id",
        ]
        missing_columns = [
            col for col in required_columns if col not in df.columns
        ]

        if missing_columns:
            logger.warning(
                "Отсутствуют обязательные колонки",
                extra={
                    "missing_columns": missing_columns,
                    "available_columns": list(df.columns),
                },
            )
            raise CsvParsingError(
                csv_path,
                f"Missing required columns: {', '.join(missing_columns)}",
            )

        return df

    def _detect_file_encoding(self, file_path: Path) -> str:
        """
        Определяет кодировку файла перебором распространённых кодировок.
        Возвращает "utf-8" по умолчанию, если ни одна не подошла.

        Args:
            file_path: Путь к файлу

        Returns:
            str: Определенная кодировка
        """
        # Простые проверки наиболее распространенных кодировок

        for encoding in COMMON_ENCODINGS:
            try:
                with file_path.open("r", encoding=encoding) as f:
                    f.read(1024)  # Читаем небольшой кусочек
                logger.debug(
                    "Detected encoding",
                    extra={"encoding": encoding, "file": str(file_path)},
                )
            except UnicodeDecodeError:
                continue
            else:
                return encoding
        # По умолчанию возвращаем utf-8
        logger.warning(
            "Could not detect encoding, falling back to utf-8",
            extra={"file": str(file_path)},
        )
        return "utf-8"

    def _validate_data_frame(self, df: DataFrame, csv_path: Path) -> None:
        """Проверяет, что DataFrame не пустой."""
        if len(df) == 0:
            logger.warning(f"CSV файл пуст: {csv_path}")
            raise CsvParsingError(csv_path, "Файл не содержит данных")

    def _load_dataframe_to_db(
        self, df: DataFrame, sync_engine: Engine, chunksize: int
    ) -> int:
        """
        Выполняет TRUNCATE таблицы и вставку данных из DataFrame.

        Args:
            df: DataFrame для загрузки
            sync_engine: Синхронный движок
            chunksize:

        Returns:
            int: Количество загруженных строк
        """
        logger.debug(
            "Load DataFrame in db",
            extra={
                "dataframe_rows": len(df),
                "dataframe_columns": len(df.columns),
            },
        )
        with sync_engine.connect() as conn:
            trans = conn.begin()
            try:
                # 1. Очистка таблицы
                conn.execute(
                    text(
                        "TRUNCATE TABLE supplier_product_codes "
                        "RESTART IDENTITY"
                    )
                )

                # 2. Вставка данных (method='multi' для ускорения)
                rows_loaded = df.to_sql(
                    name="supplier_product_codes",
                    con=conn,
                    if_exists="append",
                    index=False,
                    method="multi",
                    chunksize=chunksize,
                )
                trans.commit()
                logger.debug(
                    "Data inserted",
                    extra={"rows": rows_loaded, "chunksize": chunksize},
                )
            except Exception as e:
                trans.rollback()
                logger.error(
                    "DB load failed",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                error_message = f"Database load error: {e}"
                raise DatabaseLoadError(error_message) from e
            else:
                return int(rows_loaded)


# ===== Dependency =====
def get_supplier_product_codes_repo(
    session: Annotated[AsyncSession, Depends(get_session_generator)],
) -> SupplierProductCodeRepository:
    return SupplierProductCodeRepository(session)
