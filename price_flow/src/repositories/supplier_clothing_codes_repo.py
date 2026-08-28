import time

from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Any

import pandas as pd

from fastapi import Depends
from pandas import DataFrame
from psycopg2.extras import execute_values
from sqlalchemy import Engine, text
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions.database import DatabaseLoadError
from common.exceptions.file import CsvParsingError, FileAppNotFoundError
from core.logger import get_logger
from db.postgres import get_session_generator, run_sync_db_operation


logger = get_logger(__name__)

# ===== Константы =====
DEFAULT_CHUNKSIZE: int = 5000
COMMON_ENCODINGS: tuple[str, ...] = (
    "utf-8-sig",
    "utf-8",
    "cp1251",
    "windows-1251",
    "iso-8859-1",
)
CLOTHING_CODES_COLUMNS: tuple[str, ...] = (
    "id",
    "code",
    "name",
    "category",
    "subcategory",
    "supplier_id",
    "product_summary",
    "size",
    "color",
    "supplier_code",
    "description",
)
REQUIRED_COLUMNS: tuple[str, ...] = (
    "id",
    "code",
    "name",
    "supplier_id",
    "product_summary",
)
INTEGER_COLUMNS: tuple[str, ...] = ("id", "code", "supplier_id")
OPTIONAL_STRING_COLUMNS: tuple[str, ...] = (
    "category",
    "subcategory",
    "size",
    "color",
    "supplier_code",
    "description",
)
TABLE_NAME: str = "supplier_clothing_codes"
TRUNCATE_SQL: str = "TRUNCATE TABLE supplier_clothing_codes RESTART IDENTITY"
SETVAL_SQL: str = (
    "SELECT setval("
    "pg_get_serial_sequence('supplier_clothing_codes', 'id'), "
    "COALESCE((SELECT MAX(id) FROM supplier_clothing_codes), 1), "
    "true)"
)


class SupplierClothingCodeRepository:
    """Репозиторий массовой загрузки supplier_clothing_codes в PostgreSQL."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load_from_csv_with_truncate(
        self,
        csv_path: str | Path,
        chunksize: int = DEFAULT_CHUNKSIZE,
    ) -> dict[str, Any]:
        """
        Очищает таблицу и загружает данные из CSV пакетами.

        Args:
            csv_path: Путь к CSV-файлу.
            chunksize: Размер пакета вставки.

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
            "Starting clothing codes CSV load with truncate",
            extra={"file": str(csv_path), "chunksize": chunksize},
        )
        start_time = time.time()

        def _sync_load(sync_engine: Engine) -> dict[str, Any]:
            rows_loaded = self._load_csv_to_db(
                csv_path, sync_engine, chunksize
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
            result = await run_sync_db_operation(_sync_load)
            logger.info(
                "Clothing codes CSV loaded with truncate",
                extra={
                    "table": TABLE_NAME,
                    "rows": result["rows_loaded"],
                    "time_ms": result["processing_time_ms"],
                    "file": str(csv_path),
                },
            )
        except (CsvParsingError, FileAppNotFoundError, DatabaseLoadError):
            raise
        except Exception as e:
            logger.error(
                "Failed to load clothing codes CSV with truncate",
                extra={"error": str(e), "file": str(csv_path)},
                exc_info=True,
            )
            error_message = f"Error loading CSV: {e}"
            raise DatabaseLoadError(error_message) from e
        else:
            return result

    # ----- Приватные методы -----

    def _load_csv_to_db(
        self, csv_path: Path, sync_engine: Engine, chunksize: int
    ) -> int:
        """Читает CSV чанками и вставляет в таблицу в одной транзакции."""
        encoding = self._detect_file_encoding(csv_path)
        separator = self._detect_separator(csv_path, encoding)
        logger.debug(
            "Detected clothing codes CSV format",
            extra={
                "file_path": str(csv_path),
                "encoding": encoding,
                "separator": separator,
            },
        )
        rows_loaded = 0
        columns_validated = False

        try:
            csv_chunks = pd.read_csv(
                csv_path,
                sep=separator,
                encoding=encoding,
                dtype=str,
                on_bad_lines="warn",
                skipinitialspace=True,
                keep_default_na=False,
                chunksize=chunksize,
            )
        except (pd.errors.EmptyDataError, pd.errors.ParserError) as e:
            raise CsvParsingError(
                csv_path, f"Формат файла не соответствует CSV: {e}"
            ) from e

        with sync_engine.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(text(TRUNCATE_SQL))
                for chunk in csv_chunks:
                    if not columns_validated:
                        self._validate_columns(chunk, csv_path)
                        columns_validated = True
                    prepared = self.prepare_dataframe(chunk)
                    if prepared.empty:
                        continue
                    inserted = prepared.to_sql(
                        name=TABLE_NAME,
                        con=conn,
                        if_exists="append",
                        index=False,
                        method=self._psql_fast_insert,
                        chunksize=chunksize,
                    )
                    rows_loaded += (
                        inserted if inserted is not None else len(prepared)
                    )
                if not columns_validated or rows_loaded == 0:
                    self._raise_empty_csv(csv_path)
                conn.execute(text(SETVAL_SQL))
                trans.commit()
            except CsvParsingError:
                trans.rollback()
                raise
            except Exception as e:
                trans.rollback()
                logger.error(
                    "Clothing codes bulk replace failed",
                    extra={
                        "row_count": rows_loaded,
                        "chunksize": chunksize,
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )
                error_message = f"Database load error: {e}"
                raise DatabaseLoadError(error_message) from e

        logger.debug(
            "Clothing codes bulk replace completed",
            extra={"rows": rows_loaded, "chunksize": chunksize},
        )
        return rows_loaded

    @staticmethod
    def _detect_separator(csv_path: Path, encoding: str) -> str:
        """Определяет разделитель по первой строке заголовка."""
        with csv_path.open("r", encoding=encoding) as csv_file:
            header = csv_file.readline()
        comma_count = header.count(",")
        semicolon_count = header.count(";")
        return ";" if semicolon_count > comma_count else ","

    @staticmethod
    def _detect_file_encoding(file_path: Path) -> str:
        """Определяет кодировку файла перебором распространённых кодировок."""
        for encoding in COMMON_ENCODINGS:
            try:
                with file_path.open("r", encoding=encoding) as file_obj:
                    file_obj.read(1024)
            except UnicodeDecodeError:
                continue
            else:
                return encoding
        logger.warning(
            "Could not detect encoding, falling back to utf-8",
            extra={"file": str(file_path)},
        )
        return "utf-8"

    def _validate_columns(self, df: DataFrame, csv_path: Path) -> None:
        """Проверяет наличие обязательных колонок."""
        df.columns = df.columns.str.strip().str.lower()
        missing_columns = [
            col for col in REQUIRED_COLUMNS if col not in df.columns
        ]
        if missing_columns:
            logger.warning(
                "Clothing codes CSV is missing required columns",
                extra={
                    "missing_columns": missing_columns,
                    "available_columns": list(df.columns),
                },
            )
            raise CsvParsingError(
                csv_path,
                f"Missing required columns: {', '.join(missing_columns)}",
            )

    @staticmethod
    def _raise_empty_csv(csv_path: Path) -> None:
        """Бросает ошибку, если CSV не содержит строк данных."""
        raise CsvParsingError(csv_path, "Файл не содержит данных")

    @staticmethod
    def prepare_dataframe(df: DataFrame) -> DataFrame:
        """
        Нормализует чанк CSV: типы, пустые строки, набор колонок.

        Args:
            df: Сырой чанк из pandas.

        Returns:
            DataFrame, готовый к вставке в таблицу.
        """
        prepared = df.copy()
        prepared.columns = prepared.columns.str.strip().str.lower()
        extra_columns = [
            col
            for col in prepared.columns
            if col not in CLOTHING_CODES_COLUMNS
        ]
        if extra_columns:
            prepared = prepared.drop(columns=extra_columns)
        for column in OPTIONAL_STRING_COLUMNS:
            if column in prepared.columns:
                values = prepared[column].astype(object)
                empty_mask = values.isna() | values.eq("")
                values = values.mask(empty_mask, None)
                prepared[column] = values
        for column in ("name", "product_summary"):
            if column in prepared.columns:
                prepared[column] = prepared[column].str.strip()
        for column in INTEGER_COLUMNS:
            prepared[column] = pd.to_numeric(prepared[column], errors="raise")
        ordered = [
            col for col in CLOTHING_CODES_COLUMNS if col in prepared.columns
        ]
        return prepared[ordered]

    @staticmethod
    def _psql_fast_insert(
        table: Any,
        conn: Any,
        keys: list[str],
        data_iter: Iterable[tuple[Any, ...]],
    ) -> int | None:
        """
        Вставляет данные через PostgreSQL execute_values.

        Имена таблицы и колонок берутся из модели и не зависят от
        пользовательского ввода.
        """
        dbapi_conn = conn.connection
        cursor = dbapi_conn.cursor()
        try:
            sql = f"INSERT INTO {table.name} ({', '.join(keys)}) VALUES %s"  # noqa: S608
            execute_values(cursor, sql, data_iter, page_size=DEFAULT_CHUNKSIZE)
        finally:
            cursor.close()
        return None


def get_supplier_clothing_codes_repo(
    session: Annotated[AsyncSession, Depends(get_session_generator)],
) -> SupplierClothingCodeRepository:
    """Фабрика репозитория кодов одежды."""
    return SupplierClothingCodeRepository(session)
