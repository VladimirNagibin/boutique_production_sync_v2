import asyncio
import re
import sqlite3
import time

from contextlib import closing
from pathlib import Path
from typing import Any

import pandas as pd

from pandas import DataFrame

from common.exceptions.app_exceptions import DatabaseLoadError
from common.exceptions.file import CsvParsingError, FileAppNotFoundError
from common.logger import logger
from core.settings import settings
from db.factory import AsyncDatabaseFactory
from interfaces.db.base import IDatabaseManager


class SupplierCodesRepo:
    def __init__(
        self, db_path: str = str(settings.sqlite.sqlite_file)
    ) -> None:
        self.db_path = db_path
        self._db_manager: IDatabaseManager | None = None

    async def _get_db_manager(self) -> IDatabaseManager:
        """Lazy initialization of database manager."""
        if self._db_manager is None:
            self._db_manager = await AsyncDatabaseFactory.get_manager()
        return self._db_manager

    async def load_data(
        self,
        file_path: str | Path,
        table_name: str = "supplier_product_codes",
    ) -> dict[str, Any]:
        """
        Загружает данные из CSV файла в таблицу базы данных.

        Args:
            file_path: Путь к CSV файлу
            table_name: Имя целевой таблицы

        Returns:
            Dict с результатами загрузки

        Raises:
            FileNotFoundError: Если файл не существует
            ValueError: Если файл пуст или имеет неверный формат
            RuntimeError: Если произошла ошибка при загрузке данных
        """
        csv_path = Path(file_path)

        # Валидация имени таблицы для защиты от SQL Injection
        self._validate_table_name(table_name)

        logger.info(
            "Начало загрузки данных из CSV",
            extra={
                "file_path": str(csv_path),
                "table_name": table_name,
                "db_path": str(self.db_path),
            },
        )

        # Проверка существования файла
        if not csv_path.exists():
            error_msg = f"CSV файл не найден: {csv_path}"
            logger.error(error_msg)
            raise FileAppNotFoundError(csv_path, error_msg)

        if not csv_path.is_file():
            error_msg = f"Путь не является файлом: {csv_path}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Запускаем тяжелую операцию в отдельном потоке
        try:
            # Запускаем синхронную операцию в отдельном потоке
            await self._get_db_manager()
            result = await asyncio.to_thread(
                self._sync_load_operation, csv_path, table_name
            )

            logger.info(
                "Данные успешно загружены",
                extra={
                    "file_path": str(csv_path),
                    "table_name": table_name,
                    "rows_loaded": result["rows_loaded"],
                    "processing_time_ms": result.get("processing_time_ms", 0),
                    "columns_loaded": result.get("columns_loaded", []),
                },
            )

        except (ValueError, CsvParsingError, FileAppNotFoundError) as e:
            # Ошибки валидации данных и парсинга
            logger.warning(f"Ошибка обработки данных: {e}")
            raise

        except DatabaseLoadError as e:
            # Ошибки базы данных
            logger.error(f"Ошибка базы данных: {e}")
            raise

        except Exception as e:
            error_msg = f"Неожиданная ошибка при загрузке {csv_path}: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e
        else:
            return result

    def _validate_table_name(self, name: str) -> None:
        """
        Валидирует имя таблицы, чтобы предотвратить SQL Injection.
        Разрешает только буквы, цифры и подчеркивания.
        """
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name):
            error_message = f"Недопустимое имя таблицы: {name}"
            raise ValueError(error_message)

    def _sync_load_operation(
        self, csv_path: Path, table_name: str
    ) -> dict[str, Any]:
        """
        Синхронная операция загрузки данных.

        Args:
            csv_path: Путь к CSV файлу
            table_name: Имя целевой таблицы

        Returns:
            Dict с результатами загрузки
        """
        start_time = time.time()

        logger.debug(
            "Начало синхронной загрузки данных",
            extra={"file_path": str(csv_path), "table_name": table_name},
        )

        with closing(sqlite3.connect(str(self.db_path))) as conn:
            # Настраиваем соединение для лучшей производительности
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA cache_size=-2000")

            # Получаем информацию о таблице до загрузки
            table_info_before = self._get_table_info(conn, table_name)

            # Читаем CSV файл
            df = self._read_csv_file(csv_path)

            # Загружаем данные в базу
            rows_loaded = self._load_dataframe_to_db(df, conn, table_name)

            # Получаем информацию о таблице после загрузки
            table_info_after = self._get_table_info(conn, table_name)

            processing_time_ms = int((time.time() - start_time) * 1000)

            result: dict[str, Any] = {
                "status": "success",
                "rows_loaded": rows_loaded,
                "table_name": table_name,
                "processing_time_ms": processing_time_ms,
                "file_path": str(csv_path),
                "file_size_bytes": csv_path.stat().st_size,
                "dataframe_shape": df.shape,
                "dataframe_columns": list(df.columns),
                "table_info_before": table_info_before,
                "table_info_after": table_info_after,
                "rows_per_second": (
                    rows_loaded / (processing_time_ms / 1000)
                    if processing_time_ms > 0
                    else 0
                ),
            }

            logger.debug(
                "Синхронная загрузка завершена",
                extra={
                    "rows_loaded": rows_loaded,
                    "processing_time_ms": processing_time_ms,
                    "dataframe_shape": df.shape,
                },
            )

            return result

    def _get_table_info(
        self, conn: sqlite3.Connection, table_name: str
    ) -> dict[str, Any]:
        """
        Получает информацию о таблице.

        Args:
            conn: Соединение с базой данных
            table_name: Имя таблицы

        Returns:
            Dict с информацией о таблице
        """
        try:
            # Получаем количество строк
            cursor = conn.execute(
                f"SELECT COUNT(*) as count FROM {table_name}"  # noqa: S608 # nosec S608
            )
            row_count = cursor.fetchone()[0]
            cursor.close()

            # Получаем информацию о колонках
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            cursor.close()

            return {
                "row_count": row_count,
                "column_count": len(columns),
                "columns": [col[1] for col in columns],  # Имена колонок
            }
        except sqlite3.Error as e:
            logger.warning(
                f"Не удалось получить информацию о таблице {table_name}: {e}"
            )
            return {"row_count": 0, "column_count": 0, "columns": []}

    def _read_csv_file(self, csv_path: Path) -> DataFrame:
        """
        Читает CSV файл с обработкой ошибок и логированием.

        Args:
            csv_path: Путь к CSV файлу

        Returns:
            DataFrame: Прочитанные данные

        Raises:
            pd.errors.EmptyDataError: Если файл пуст
            pd.errors.ParserError: Если ошибка парсинга
        """
        logger.debug(f"Чтение CSV файла: {csv_path}")

        try:
            # Пробуем определить кодировку файла
            encoding = self._detect_file_encoding(csv_path)

            logger.debug(
                f"Определена кодировка файла: {encoding}",
                extra={"file_path": str(csv_path)},
            )

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

            # Логируем информацию о прочитанных данных
            logger.info(
                "CSV файл успешно прочитан",
                extra={
                    "file_path": str(csv_path),
                    "rows": len(df),
                    "columns": len(df.columns),
                    "column_names": list(df.columns),
                    "encoding": encoding,
                    "memory_usage_mb": df.memory_usage(deep=True).sum()
                    / (1024 * 1024),
                },
            )

            # Проверяем наличие данных
            self._validate_data_frame(df, csv_path)

            # Очищаем имена колонок
            df.columns = df.columns.str.strip().str.lower()

            # Проверяем необходимые колонки
            required_columns = [
                "code",
                "name",
                "supplier_id",
                "id",
                "category",
                "subcategory",
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
        else:
            return df

    def _validate_data_frame(self, df: DataFrame, csv_path: Path) -> None:
        if len(df) == 0:
            logger.warning(f"CSV файл пуст: {csv_path}")
            raise CsvParsingError(csv_path, "Файл не содержит данных")

    def _detect_file_encoding(self, file_path: Path) -> str:
        """
        Определяет кодировку файла.

        Args:
            file_path: Путь к файлу

        Returns:
            str: Определенная кодировка
        """
        # Простые проверки наиболее распространенных кодировок
        common_encodings = ["utf-8", "cp1251", "windows-1251", "iso-8859-1"]

        for encoding in common_encodings:
            try:
                with file_path.open("r", encoding=encoding) as f:
                    f.read(1024)  # Читаем небольшой кусочек
            except UnicodeDecodeError:
                continue
            else:
                return encoding
        # По умолчанию возвращаем utf-8
        logger.warning(
            f"Не удалось определить кодировку для {file_path}, "
            "используется utf-8"
        )
        return "utf-8"

    def _load_dataframe_to_db(
        self, df: DataFrame, conn: sqlite3.Connection, table_name: str
    ) -> int:
        """
        Загружает DataFrame в базу данных.

        Args:
            df: DataFrame для загрузки
            conn: Соединение с базой данных
            table_name: Имя целевой таблицы

        Returns:
            int: Количество загруженных строк
        """
        logger.debug(
            "Загрузка DataFrame в базу данных",
            extra={
                "table_name": table_name,
                "dataframe_rows": len(df),
                "dataframe_columns": len(df.columns),
            },
        )

        # Оптимизация типов данных
        df = self._optimize_dataframe_types(df)
        logger.debug(
            f"Начало записи в таблицу {table_name} ({len(df)} строк)"
        )
        try:
            # Загружаем данные в базу
            rows_loaded: int | None = df.to_sql(
                name=table_name,
                con=conn,
                if_exists="replace",  # append replace
                index=False,
                chunksize=10000,
                method="multi",  # Множественная вставка для скорости
            )

            # Создаем индексы после загрузки данных для производительности
            self._create_indexes(conn, table_name)

            logger.debug(
                "DataFrame загружен в базу данных",
                extra={"table_name": table_name, "rows_loaded": rows_loaded},
            )

        except sqlite3.Error as e:
            logger.error(f"Ошибка при записи в БД: {e}", exc_info=True)
            error_message = f"Не удалось сохранить данные в базу: {e}"
            raise DatabaseLoadError(error_message) from e
        else:
            return rows_loaded or 0

    def _optimize_dataframe_types(self, df: DataFrame) -> DataFrame:
        """
        Оптимизирует типы данных в DataFrame.

        Args:
            df: Исходный DataFrame

        Returns:
            DataFrame: Оптимизированный DataFrame
        """
        # Создаем копию, чтобы не модифицировать оригинал
        result_df = df.copy()
        column_types = {
            "supplier_id": "Int64",  # Int64 поддерживает NaN
            "code": "Int64",
            "id": "Int64",
        }
        # Применяем типы для существующих колонок
        for column, dtype in column_types.items():
            if column in result_df.columns:
                try:
                    # Сначала конвертируем в numeric, затем в Int64
                    result_df[column] = pd.to_numeric(
                        result_df[column], errors="coerce"
                    )
                    result_df[column] = result_df[column].astype(dtype)
                except Exception as e:  # noqa: BLE001
                    logger.debug(
                        f"Ошибка при конвертации колонки '{column}': {e}"
                    )
        return result_df

    def _create_indexes(
        self, conn: sqlite3.Connection, table_name: str
    ) -> None:
        """
        Создает индексы для таблицы.

        Args:
            conn: Соединение с базой данных
            table_name: Имя таблицы
        """
        indexes = [
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_supplier_code "
            f"ON {table_name} (supplier_id, code)",
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_name "
            f"ON {table_name} (name)",
            f"CREATE INDEX IF NOT EXISTS idx_{table_name}_group "
            f"ON {table_name} (category)",
        ]

        for index_sql in indexes:
            try:
                conn.execute(index_sql)
                logger.debug(f"Создан индекс: {index_sql}")
            except sqlite3.Error as e:
                logger.warning(f"Не удалось создать индекс: {e}")

    def get_supplier_data(self, supplier_id: int) -> pd.DataFrame:
        """Получает данные поставщика из SQLite.

        Args:
            supplier_id: Идентификатор поставщика

        Returns:
            DataFrame с колонками: code, category, subcategory
        """
        conn = sqlite3.connect(settings.DB_SQLITE_PATH)
        query = """
        SELECT code, category, subcategory
        FROM supplier_product_codes
        WHERE supplier_id = ?
        """
        df_db = pd.read_sql_query(query, conn, params=(supplier_id,))
        conn.close()

        # Преобразуем code в строку для гарантированного совпадения
        df_db["code"] = df_db["code"].astype(str).str.strip()

        return df_db


def get_supplier_codes_repo() -> SupplierCodesRepo:
    return SupplierCodesRepo()
