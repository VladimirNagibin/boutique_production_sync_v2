import sqlite3
import time

from pathlib import Path
from typing import Any

import pandas as pd

from pandas import DataFrame

from core.exceptions import DatabaseLoadError, FileAppNotFoundError
from core.logger import logger
from core.settings import settings
from db.factory import AsyncDatabaseFactory
from interfaces.db.base import IDatabaseManager
from schemas.supplier_schemas import SupplierProduct, SupplierProductPrice


class SupplierClothingRepo:
    def __init__(self, db_path: str = str(settings.DB_SQLITE_PATH)) -> None:  # type: ignore
        self.db_path = db_path
        self._db_manager: IDatabaseManager | None = None

    async def _get_db_manager(self) -> IDatabaseManager:
        """Lazy initialization of database manager."""
        if self._db_manager is None:
            self._db_manager = await AsyncDatabaseFactory.get_manager()
        return self._db_manager

    async def transfer_with_column_rename(self):
        """
        Переносит данные с переименованием колонок

        table_mapping = {
            'source_table': {
                'target_table': 'new_table_name',
                'column_mapping': {
                    'old_col1': 'new_col1',
                    'old_col2': 'new_col2',
                    # ...
                }
            }
        }
        """
        SOURCE_DB_FILE = "db.sqlite3"
        source_db = Path(settings.BASE_DIR) / f"data/{SOURCE_DB_FILE}"
        target_db = settings.DB_SQLITE_PATH
        table_mapping: dict[str, Any] = {
            'products_codesupplierfile': {
                'target_table': 'supplier_clothing_codes',
                'column_mapping': {
                    'id': 'id',
                    'code': 'code',
                    'name': 'name',
                    'brand': 'category',
                    'subgroup': 'subcategory',
                    'supplier': 'supplier_id',
                    'product_summary': 'product_summary',
                    'size': 'size',
                    'color': 'color',
                }
            }
        }

        source_conn = sqlite3.connect(source_db)
        target_conn = sqlite3.connect(target_db)

        for source_table, config in table_mapping.items():
            target_table = config.get('target_table', source_table)
            column_mapping = config['column_mapping']

            # Создаем список исходных колонок
            source_cols = ', '.join(column_mapping.keys())

            # Создаем список целевых колонок
            # target_cols = ', '.join(column_mapping.values())

            # Читаем данные
            query = f"SELECT {source_cols} FROM {source_table}"
            df = pd.read_sql_query(query, source_conn)

            # Переименовываем колонки
            df.columns = list(column_mapping.values())

            # Записываем в целевую базу
            df.to_sql(target_table, target_conn, if_exists='replace', index=False)

        source_conn.close()
        target_conn.close()

    async def get_max_code_async(self, supplier_id: int) -> int:
        """
        Асинхронно находит максимальное значение code для поставщика

        Использование:
        max_code = await get_max_code_async(1)
        """

        try:
            db_manager = await self._get_db_manager()
            query = """
            SELECT MAX(code)
            FROM supplier_clothing_codes
            WHERE supplier_id = ?
            """

            result = await db_manager.execute_query(query, (supplier_id,))
            if result and result[0]:
                max_code = result[0]["MAX(code)"] if result[0]["MAX(code)"] is not None else 0
                print(f"Максимальный код для поставщика {supplier_id}: {max_code}")

                return max_code
            else:
                print(f"Для поставщика {supplier_id} нет записей")
                return 0

        except Exception as e:
            print(f"Ошибка: {e}")
            return 0

    async def clear_supplier_price(self, supplier_id: int) -> None:
        """
        Асинхронно очищает таблицу прайса поставщика
        """

        try:
            db_manager = await self._get_db_manager()
            query = """
            DELETE FROM supplier_price
            WHERE supplier_id = ?
            """

            result = await db_manager.execute_query(query, (supplier_id,))
            print(result)

        except Exception as e:
            print(f"Ошибка: {e}")

    async def get_supplier_product(
        self,
        supplier_id: int,
        product_summary: str,
        size: str,
        color: str,
    ) -> SupplierProduct | None:
        """
        Находит код, группу и подгруппу товара поставщика по наименованию
        """
        try:
            db_manager = await self._get_db_manager()
            search_name = f'{product_summary} {size} {color}'.strip()
            query = """
            SELECT code, category, subcategory
            FROM supplier_clothing_codes
            WHERE supplier_id = ? AND name = ?
            """
            params_tuple: tuple[Any, ...] = (supplier_id, search_name)
            result = await db_manager.execute_query(query, params_tuple)
            if result and result[0]:
                # print("OK")
                return SupplierProduct(
                    code=result[0]["code"],
                    category=result[0]["category"],
                    subcategory=result[0]["subcategory"],
                )
            else:
                # print("")
                return None

        except Exception as e:
            print(f"Ошибка: {e}")
        return None

    async def get_supplier_category_by_code(
        self,
        supplier_id: int,
        code: int,
    ) -> SupplierProduct | None:
        """
        Находит код, группу и подгруппу товара поставщика по наименованию
        """
        try:
            db_manager = await self._get_db_manager()
            query = """
            SELECT category, subcategory
            FROM supplier_product_codes
            WHERE supplier_id = ? AND code = ?
            """
            params_tuple: tuple[Any, ...] = (supplier_id, code)
            result = await db_manager.execute_query(query, params_tuple)
            if result and result[0]:
                # print("")
                return SupplierProduct(
                    code=code,
                    category=result[0]["category"],
                    subcategory=result[0]["subcategory"],
                )
            else:
                # print("")
                return None

        except Exception as e:
            print(f"Ошибка: {e}")
        return None

    async def add_supplier_price(
        self,
        supplier_prices: list[SupplierProductPrice],
        batch_size: int = 100,
        replace_duplicates: bool = True
    ) -> dict[str, Any]:
        """
        Загружает прайс в таблицу supplier_price

        Args:
            supplier_prices: список объектов SupplierProductPrice
            batch_size: размер пакета для вставки (оптимизация)
            replace_duplicates: заменить дубликаты (True) или пропустить (False)

        Returns:
            Словарь с результатами операции
        """
        if not supplier_prices:
            print("Пустой список прайсов")
            return {"inserted": 0, "skipped": 0, "errors": 0}

        try:
            db_manager = await self._get_db_manager()

            print(f"Начало загрузки {len(supplier_prices)} записей в supplier_price")

            # Статистика
            stats: dict[str, Any] = {
                "total": len(supplier_prices),
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "errors": 0,
                "supplier_ids": set(),
                "batches": 0
            }

            # Разбиваем на пакеты для оптимизации
            for i in range(0, len(supplier_prices), batch_size):
                batch = supplier_prices[i:i + batch_size]
                stats["batches"] += 1

                try:
                    if replace_duplicates:
                        # Вставка с заменой дубликатов
                        batch_result = await self._insert_batch_replace(
                            db_manager, batch, stats
                        )
                    else:
                        # Вставка с игнорированием дубликатов
                        batch_result = await self._insert_batch_ignore(
                            db_manager, batch, stats
                        )

                    print(f"Пакет {stats['batches']}: обработано {len(batch)} записей")

                except Exception as e:
                    print(f"Ошибка в пакете {stats['batches']}: {e}")
                    stats["errors"] += len(batch)

            # Собираем статистику по поставщикам
            stats["supplier_ids"] = list(stats["supplier_ids"])

            print("Загрузка завершена:")
            print(f"   Всего: {stats['total']}")
            print(f"   Вставлено: {stats['inserted']}")
            print(f"   Обновлено: {stats['updated']}")
            print(f"   Пропущено: {stats['skipped']}")
            print(f"   Ошибок: {stats['errors']}")
            print(f"   Поставщики: {stats['supplier_ids']}")

            return stats

        except Exception as e:
            print(f"Критическая ошибка загрузки: {e}")
            return {
                "status": "error",
                "error": str(e),
                "inserted": 0,
                "updated": 0,
                "skipped": 0,
                "errors": len(supplier_prices)
            }

    async def _insert_batch_replace(
        self,
        db_manager: IDatabaseManager,
        batch: list[SupplierProductPrice],
        stats: dict[str, Any]
    ) -> None:
        """
        Вставляет пакет данных с заменой дубликатов

        Использует INSERT OR REPLACE для обновления существующих записей
        Дубликаты определяются по supplier_id + code + name
        """

        # SQL для вставки с заменой
        insert_sql = """
        INSERT OR REPLACE INTO supplier_price
        (code, name, category, subcategory, supplier_id,
        product_summary, size, color, price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # Подготавливаем данные
        values: list[Any] = []
        for item in batch:
            values.append((
                item.code,
                item.name.strip(),  # Очищаем пробелы
                item.category.strip() if item.category else None,
                item.subcategory.strip() if item.subcategory else None,
                item.supplier_id,
                item.product_summary.strip(),
                item.size.strip() if item.size else None,
                item.color.strip() if item.color else None,
                round(item.price, 2)  # Округляем до 2 знаков
            ))

            # Собираем статистику
            stats["supplier_ids"].add(item.supplier_id)
        # Выполняем вставку
        try:
            await db_manager.execute_many(insert_sql, values)

            # Проверяем сколько было вставлено/обновлено
            for item in batch:
                # Проверяем существовала ли запись
                check_sql = """
                SELECT id FROM supplier_price
                WHERE supplier_id = ? AND code = ?
                """
                existing = await db_manager.execute_query(
                    check_sql,
                    (item.supplier_id, item.code)
                )

                if existing:
                    stats["updated"] += 1
                else:
                    stats["inserted"] += 1

        except sqlite3.IntegrityError as e:
            # Если ошибка целостности, пробуем вставить по одной
            print(f"Ошибка целостности пакета, вставляем по одной: {e}")
            await self._insert_one_by_one(db_manager, batch, stats, insert_sql)

    async def _insert_batch_ignore(
        self,
        db_manager: IDatabaseManager,
        batch: list[SupplierProductPrice],
        stats: dict[str, Any]
    ) -> None:
        """
        Вставляет пакет данных, игнорируя дубликаты

        Использует INSERT OR IGNORE для пропуска существующих записей
        """

        # SQL для вставки с игнорированием
        insert_sql = """
        INSERT OR IGNORE INTO supplier_price
        (code, name, category, subcategory, supplier_id,
        product_summary, size, color, price)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        # Подготавливаем данные
        values: list[Any] = []
        for item in batch:
            values.append((
                item.code,
                item.name.strip(),
                item.category.strip() if item.category else None,
                item.subcategory.strip() if item.subcategory else None,
                item.supplier_id,
                item.product_summary.strip(),
                item.size.strip() if item.size else None,
                item.color.strip() if item.color else None,
                round(item.price, 2)
            ))

            stats["supplier_ids"].add(item.supplier_id)

        # Выполняем вставку
        try:
            result = await db_manager.execute_query(insert_sql, values)

            # Считаем вставленные записи
            inserted_count = result.rowcount if hasattr(result, 'rowcount') else len(batch)
            stats["inserted"] += inserted_count
            stats["skipped"] += (len(batch) - inserted_count)

        except sqlite3.IntegrityError as e:
            print(f"Ошибка целостности, вставляем по одной: {e}")
            await self._insert_one_by_one(db_manager, batch, stats, insert_sql)

    async def _insert_one_by_one(
        self,
        db_manager: IDatabaseManager,
        batch: list[SupplierProductPrice],
        stats: dict[str, Any],
        insert_sql: str
    ) -> None:
        """
        Вставляет записи по одной (fallback при ошибках пакетной вставки)
        """

        for item in batch:
            try:
                values = (
                    item.code,
                    item.name.strip(),
                    item.category.strip() if item.category else None,
                    item.subcategory.strip() if item.subcategory else None,
                    item.supplier_id,
                    item.product_summary.strip(),
                    item.size.strip() if item.size else None,
                    item.color.strip() if item.color else None,
                    round(item.price, 2)
                )

                await db_manager.execute_query(insert_sql, values)

                # Проверяем была ли вставка
                check_sql = """
                SELECT id FROM supplier_price
                WHERE supplier_id = ? AND code = ?
                """
                existing = await db_manager.execute_query(
                    check_sql,
                    (item.supplier_id, item.code)
                )

                if existing:
                    stats["updated"] += 1
                else:
                    stats["inserted"] += 1

            except sqlite3.IntegrityError as e:
                print(f"Ошибка вставки записи: {e}")
                stats["errors"] += 1

            except Exception as e:
                print(f"Неожиданная ошибка: {e}")
                stats["errors"] += 1

    def save_price_as_is(self, excel_file_path: str | Path | None = None) -> DataFrame:
        connection = sqlite3.connect(settings.DB_SQLITE_PATH)
        data_frame = pd.read_sql('SELECT * FROM supplier_price', connection)
        # data_frame.to_excel(excel_file_path, index=False)
        return data_frame

    def save_price_for_load(self) -> DataFrame:
        connection = sqlite3.connect(settings.DB_SQLITE_PATH)
        data_frame = pd.read_sql(
            'SELECT * FROM supplier_price ORDER BY category, subcategory, name',
            connection
        )
        return data_frame

    async def load_data(
        self, file_path: str | Path, table_name: str = "supplier_price"
    ) -> dict[str, Any]:
        """
        Обновляет данные из XLSX файла в таблицу базы данных.

        Args:
            file_path: Путь к XLSX файлу
            table_name: Имя целевой таблицы

        Returns:
            Dict с результатами загрузки

        Raises:
            FileNotFoundError: Если файл не существует
            ValueError: Если файл пуст или имеет неверный формат
            RuntimeError: Если произошла ошибка при загрузке данных
        """
        xlsx_path = Path(file_path)

        # Валидация имени таблицы для защиты от SQL Injection
        # self._validate_table_name(table_name)

        logger.info(
            "Начало загрузки данных из XLSX",
            extra={
                "file_path": str(xlsx_path),
                "table_name": table_name,
                "db_path": str(self.db_path),
            },
        )

        # Проверка существования файла
        if not xlsx_path.exists():
            error_msg = f"XLSX файл не найден: {xlsx_path}"
            logger.error(error_msg)
            raise FileAppNotFoundError(xlsx_path, error_msg)

        if not xlsx_path.is_file():
            error_msg = f"Путь не является файлом: {xlsx_path}"
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Запускаем тяжелую операцию в отдельном потоке
        try:
            # Запускаем синхронную операцию в отдельном потоке
            # result = await asyncio.to_thread(
            #     self._sync_load_operation, xlsx_path, table_name
            # )
            result = await  self._sync_load_operation(xlsx_path, table_name)
            logger.info(
                "Данные успешно загружены",
                extra={
                    "file_path": str(xlsx_path),
                    "table_name": table_name,
                    # "rows_loaded": result["rows_loaded"],
                    # "processing_time_ms": result.get("processing_time_ms", 0),
                    # "columns_loaded": result.get("columns_loaded", []),
                },
            )

        except (ValueError, FileAppNotFoundError) as e:
            # Ошибки валидации данных и парсинга
            logger.warning(f"Ошибка обработки данных: {e}")
            raise

        except DatabaseLoadError as e:
            # Ошибки базы данных
            logger.error(f"Ошибка базы данных: {e}")
            raise

        except Exception as e:
            error_msg = f"Неожиданная ошибка при загрузке {xlsx_path}: {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e
        else:
            return result


    async def _sync_load_operation(self, xlsx_path: Path, table_name: str) -> dict[str, Any]:
        """
        Синхронная операция загрузки данных.

        Args:
            xlsx_path: Путь к XLSX файлу
            table_name: Имя целевой таблицы

        Returns:
            Dict с результатами загрузки
        """
        start_time = time.time()

        logger.debug(
            "Начало синхронной загрузки данных",
            extra={"file_path": str(xlsx_path), "table_name": table_name},
        )

        df = self._load_excel_data(xlsx_path)

        result = await self._update_categories(df)

        # with closing(sqlite3.connect(str(self.db_path))) as conn:
        #     # Настраиваем соединение для лучшей производительности
        #     conn.execute("PRAGMA journal_mode=WAL")
        #     conn.execute("PRAGMA synchronous=NORMAL")
        #     conn.execute("PRAGMA cache_size=-2000")

            # Получаем информацию о таблице до загрузки
            # table_info_before = self._get_table_info(conn, table_name)

            # # Читаем CSV файл
            # df = self._read_csv_file(xlsx_path)

            # # Загружаем данные в базу
            # rows_loaded = self._load_dataframe_to_db(df, conn, table_name)

            # # Получаем информацию о таблице после загрузки
            # table_info_after = self._get_table_info(conn, table_name)

            # processing_time_ms = int((time.time() - start_time) * 1000)

            # result: dict[str, Any] = {
            #     "status": "success",
            #     "rows_loaded": rows_loaded,
            #     "table_name": table_name,
            #     "processing_time_ms": processing_time_ms,
            #     "file_path": str(csv_path),
            #     "file_size_bytes": csv_path.stat().st_size,
            #     "dataframe_shape": df.shape,
            #     "dataframe_columns": list(df.columns),
            #     "table_info_before": table_info_before,
            #     "table_info_after": table_info_after,
            #     "rows_per_second": (
            #         rows_loaded / (processing_time_ms / 1000)
            #         if processing_time_ms > 0
            #         else 0
            #     ),
            # }

            # logger.debug(
            #     "Синхронная загрузка завершена",
            #     extra={
            #         "rows_loaded": rows_loaded,
            #         "processing_time_ms": processing_time_ms,
            #         "dataframe_shape": df.shape,
            #     },
            # )

        return result

    def _load_excel_data(self, excel_path: str | Path) -> pd.DataFrame:
        """
        Загрузка данных из Excel файла

        Args:
            excel_path: Путь к Excel файлу

        Returns:
            DataFrame с данными из Excel
        """
        try:
            # Загружаем Excel файл
            df = pd.read_excel(
                excel_path,
                dtype={
                    'id': 'int64',
                    'code': 'int64',
                    'name': 'str',
                    'category': 'str',
                    'subcategory': 'str',
                    'supplier_id': 'int64',
                    'product_summary': 'str',
                    'size': 'str',
                    'color': 'str',
                    'price': 'float64'
                }
            )

            logger.info(f"Загружен Excel файл: {excel_path}")
            logger.info(f"Количество строк: {len(df)}")
            logger.info(f"Колонки: {', '.join(df.columns)}")

            # Проверяем необходимые колонки
            required_columns = ['code', 'category', 'subcategory', 'supplier_id']
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                raise ValueError(f"Отсутствуют обязательные колонки: {missing_columns}")

            # Очищаем строковые данные
            string_columns = ['category', 'subcategory', 'name', 'product_summary', 'size', 'color']
            for col in string_columns:
                if col in df.columns:
                    df[col] = df[col].astype(str).str.strip()

            # Заменяем NaN на None
            df = df.where(pd.notnull(df), None)

            df['code'] = pd.to_numeric(df['code'], errors='coerce').astype('Int64')
            df['supplier_id'] = pd.to_numeric(df['supplier_id'], errors='coerce').astype('Int64')

            return df

        except FileNotFoundError:
            logger.error(f"Файл не найден: {excel_path}")
            raise
        except Exception as e:
            logger.error(f"Ошибка загрузки Excel файла: {e}")
            raise

    async def _update_categories(self, df: pd.DataFrame, batch_size: int = 1000) -> tuple[int, int]:
        """
        Обновление категорий и подкатегорий в базе данных

        Args:
            df: DataFrame с данными из Excel
            batch_size: Размер пакета для обновления

        Returns:
            Tuple: (обновлено записей, всего обработано)
        """
        try:
            db_manager = await self._get_db_manager()

            # SQL запрос на обновление
            # Обновляем category и subcategory там, где совпали code и supplier_id
            query = """
            UPDATE supplier_price
            SET category = ?,
                subcategory = ?
            WHERE code = ?
            AND supplier_id = ?
            """

            # 4. Подготовка данных для массовой вставки (executemany)
            # Формируем список кортежей: (category, subcategory, code, supplier_id)
            data_to_update: list[tuple[Any, ...]] = []

            for _, row in df.iterrows():
                # Преобразуем в стандартные Python типы (int из numpy, str из object)
                row_tuple = (
                    str(row['category']) if pd.notna(row['category']) else None,
                    str(row['subcategory']) if pd.notna(row['subcategory']) else None,
                    int(row['code']),
                    int(row['supplier_id'])
                )
                data_to_update.append(row_tuple)
            # print(data_to_update)
            # 5. Выполнение обновления
            result = await db_manager.execute_many(query, data_to_update)
            # print(result)
            await self.update_supplier_clothing()

        except Exception as e:
            print(f"Ошибка: {e}")


        #     updated_count = 0
        #     total_processed = 0

        #     # Создаем временную таблицу для данных из Excel
        #     cursor.execute("""
        #         CREATE TEMPORARY TABLE temp_excel_data (
        #             code INTEGER,
        #             category TEXT,
        #             subcategory TEXT,
        #             supplier_id INTEGER,
        #             PRIMARY KEY (code, supplier_id)
        #         )
        #     """)

        #     # Вставляем данные во временную таблицу
        #     excel_data = df[['code', 'category', 'subcategory', 'supplier_id']].to_records(index=False)
        #     cursor.executemany(
        #         "INSERT OR REPLACE INTO temp_excel_data (code, category, subcategory, supplier_id) VALUES (?, ?, ?, ?)",
        #         excel_data
        #     )

        #     logger.info(f"Загружено во временную таблицу: {len(df)} записей")

        #     # 4. ПРОВЕРКА ДАННЫХ ВО ВРЕМЕННОЙ ТАБЛИЦЕ
        #     cursor.execute("SELECT COUNT(*) FROM temp_excel_data")
        #     temp_count = cursor.fetchone()[0]
        #     logger.info(f"Фактически во временной таблице: {temp_count} записей")

        #     # 5. ПРОВЕРКА СУЩЕСТВУЮЩИХ ДАННЫХ В БАЗЕ
        #     cursor.execute("SELECT COUNT(*) FROM supplier_price")
        #     total_in_db = cursor.fetchone()[0]
        #     logger.info(f"Всего записей в supplier_price: {total_in_db}")

        #     # 6. ПРОВЕРКА СОВПАДЕНИЙ
        #     cursor.execute("""
        #         SELECT COUNT(*)
        #         FROM supplier_price sp
        #         WHERE EXISTS (
        #             SELECT 1 FROM temp_excel_data ted
        #             WHERE ted.code = sp.code
        #             AND ted.supplier_id = sp.supplier_id
        #         )
        #     """)
        #     matches_count = cursor.fetchone()[0]
        #     logger.info(f"Найдено совпадений в базе: {matches_count}")

        #     # 7. ВЫВОД ПРИМЕРОВ СОВПАДЕНИЙ (если есть)
        #     if matches_count > 0:
        #         cursor.execute("""
        #             SELECT sp.code, sp.supplier_id, sp.category, sp.subcategory,
        #                 ted.category as new_category, ted.subcategory as new_subcategory
        #             FROM supplier_price sp
        #             JOIN temp_excel_data ted ON ted.code = sp.code
        #                 AND ted.supplier_id = sp.supplier_id
        #             LIMIT 5
        #         """)
        #         examples = cursor.fetchall()
        #         logger.info("Примеры совпадений (первые 5):")
        #         for ex in examples:
        #             logger.info(f"  code={ex[0]}, supplier={ex[1]}, "
        #                     f"старая категория='{ex[2]}', новая='{ex[3]}', "
        #                     f"старая подкатегория='{ex[4]}', новая='{ex[5]}'")

        #     # Обновляем основную таблицу данными из временной
        #     cursor.execute("""
        #         UPDATE supplier_price
        #         SET
        #             category = COALESCE((SELECT category FROM temp_excel_data
        #                             WHERE temp_excel_data.code = supplier_price.code
        #                             AND temp_excel_data.supplier_id = supplier_price.supplier_id),
        #                             supplier_price.category),
        #             subcategory = COALESCE((SELECT subcategory FROM temp_excel_data
        #                                 WHERE temp_excel_data.code = supplier_price.code
        #                                 AND temp_excel_data.supplier_id = supplier_price.supplier_id),
        #                                 supplier_price.subcategory)
        #         WHERE EXISTS (
        #             SELECT 1 FROM temp_excel_data
        #             WHERE temp_excel_data.code = supplier_price.code
        #             AND temp_excel_data.supplier_id = supplier_price.supplier_id
        #         )
        #     """)

        #     updated_count = cursor.rowcount

        #     # Коммитим изменения
        #     conn.commit()

        #     logger.info(f"Обновлено записей: {updated_count}")

        #     # Очищаем временную таблицу
        #     cursor.execute("DROP TABLE IF EXISTS temp_excel_data")

        #     return updated_count, len(df)

    async def update_supplier_clothing(self):
        """
        Обновляет или добавляет записи в supplier_clothing_codes из supplier_price.
        Совпадение происходит по связке code + supplier_id.
        """

        try:
            db_manager = await self._get_db_manager()

            # SQL запрос для вставки или обновления
            # Мы берем только те поля, которые есть в source таблице (supplier_price).
            # Поля supplier_code и description в целевой таблице НЕ обновляются данными из источника,
            # так как их там нет. Они останутся NULL (для новых) или сохранят старые значения (при обновлении).
            # query = """
            # INSERT INTO supplier_clothing_codes (
            #     code, name, category, subcategory, supplier_id,
            #     product_summary, size, color
            # )
            # SELECT
            #     code, name, category, subcategory, supplier_id,
            #     product_summary, size, color
            # FROM supplier_price
            # ON CONFLICT (unique_supplier_code) DO UPDATE SET
            #     name = excluded.name,
            #     category = excluded.category,
            #     subcategory = excluded.subcategory,
            #     product_summary = excluded.product_summary,
            #     size = excluded.size,
            #     color = excluded.color
            # """
            query = """
            INSERT OR IGNORE INTO supplier_clothing_codes (
                code, name, category, subcategory, supplier_id,
                product_summary, size, color
            )
            SELECT
                code, name, category, subcategory, supplier_id,
                product_summary, size, color
            FROM supplier_price
            """
            result = await db_manager.execute_query_(query)
            print(result)

        except Exception as e:
            print(f"Ошибка: {e}")

    async def update_supplier_clothing_(self):
        try:
            db_manager = await self._get_db_manager()

            # Разделяем запрос на отдельные операции
            queries = [
                # 1. Обновляем существующие записи
                """
                UPDATE supplier_clothing_codes
                SET name = (SELECT name FROM supplier_price
                        WHERE supplier_price.code = supplier_clothing_codes.code
                        AND supplier_price.supplier_id = supplier_clothing_codes.supplier_id),
                    category = (SELECT category FROM supplier_price
                            WHERE supplier_price.code = supplier_clothing_codes.code
                            AND supplier_price.supplier_id = supplier_clothing_codes.supplier_id),
                    subcategory = (SELECT subcategory FROM supplier_price
                                WHERE supplier_price.code = supplier_clothing_codes.code
                                AND supplier_price.supplier_id = supplier_clothing_codes.supplier_id),
                    product_summary = (SELECT product_summary FROM supplier_price
                                    WHERE supplier_price.code = supplier_clothing_codes.code
                                    AND supplier_price.supplier_id = supplier_clothing_codes.supplier_id),
                    size = (SELECT size FROM supplier_price
                        WHERE supplier_price.code = supplier_clothing_codes.code
                        AND supplier_price.supplier_id = supplier_clothing_codes.supplier_id),
                    color = (SELECT color FROM supplier_price
                            WHERE supplier_price.code = supplier_clothing_codes.code
                            AND supplier_price.supplier_id = supplier_clothing_codes.supplier_id)
                WHERE EXISTS (
                    SELECT 1 FROM supplier_price
                    WHERE supplier_price.code = supplier_clothing_codes.code
                    AND supplier_price.supplier_id = supplier_clothing_codes.supplier_id
                )
                """,

                # 2. Добавляем новые записи
                """
                INSERT INTO supplier_clothing_codes (
                    code, name, category, subcategory, supplier_id,
                    product_summary, size, color
                )
                SELECT code, name, category, subcategory, supplier_id,
                    product_summary, size, color
                FROM supplier_price
                WHERE NOT EXISTS (
                    SELECT 1 FROM supplier_clothing_codes
                    WHERE supplier_clothing_codes.code = supplier_price.code
                    AND supplier_clothing_codes.supplier_id = supplier_price.supplier_id
                )
                """
            ]

            for query in queries:
                result = await db_manager.execute_query(query)
                print(f"{result}===================")

            return {"success": True, "message": "Обновление завершено"}

        except Exception as e:
            print(f"Ошибка: {e}")
            return {"success": False, "error": str(e)}

    async def fix_supplier_id_type(self):
        """Упрощенная версия миграции"""
        try:
            db_manager = await self._get_db_manager()

            # 1. Проверяем текущее состояние
            tables = await db_manager.execute_query(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            print("Доступные таблицы:", [t['name'] for t in tables])

            # 2. Выполняем миграцию в одной транзакции
            # await db_manager.execute_query("BEGIN TRANSACTION")

            # try:
            # Создаем новую таблицу с нужной структурой
            await db_manager.execute_query("""
                CREATE TABLE IF NOT EXISTS supplier_clothing_codes_new (
                    "id" INTEGER PRIMARY KEY AUTOINCREMENT,
                    "code" INTEGER NOT NULL CHECK (code > 0),
                    "name" TEXT,
                    "category" TEXT,
                    "subcategory" TEXT,
                    "supplier_id" INTEGER,
                    "product_summary" TEXT,
                    "size" TEXT,
                    "color" TEXT,
                    supplier_code VARCHAR(255) DEFAULT '',
                    description TEXT DEFAULT '',
                    CONSTRAINT unique_supplier_code UNIQUE (code, supplier_id)
                )
            """)

            # Копируем данные из старой таблицы в новую
            # await db_manager.execute_query("""
            #     INSERT INTO supplier_clothing_codes_new (
            #         code, name, category, subcategory, supplier_id,
            #         product_summary, size, color, supplier_code, description
            #     )
            #     SELECT
            #         code, name, category, subcategory, supplier_id,
            #         product_summary, size, color, supplier_code, description
            #     FROM supplier_clothing_codes
            # """)
            # await db_manager.execute_query_("""
            #     INSERT INTO supplier_clothing_codes_new
            #     SELECT * FROM supplier_clothing_codes
            # """)
            # return
            # Удаляем старую таблицу
            await db_manager.execute_query("DROP TABLE supplier_clothing_codes")

            # Переименовываем новую таблицу
            await db_manager.execute_query("ALTER TABLE supplier_clothing_codes_new RENAME TO supplier_clothing_codes")

            # Создаем индексы
            await db_manager.execute_query("""
                CREATE INDEX IF NOT EXISTS idx_supplier_code_clothing
                ON supplier_clothing_codes (supplier_id, code)
            """)

            await db_manager.execute_query("""
                CREATE INDEX IF NOT EXISTS idx_product_name_clothing
                ON supplier_clothing_codes (name)
            """)

            # Коммитим
        #    await db_manager.execute_query("COMMIT")

            print("Миграция успешно завершена")
            return {"success": True}

            # except Exception as inner_error:
            #     # Откатываем при любой ошибке внутри транзакции
            #     # await db_manager.execute_query("ROLLBACK")
            #     raise inner_error

        except Exception as e:
            print(f"Ошибка миграции: {e}")
            return {"success": False, "error": str(e)}


def get_supplier_codes_repo() -> SupplierClothingRepo:
    return SupplierClothingRepo()
