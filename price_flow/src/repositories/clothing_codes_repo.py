from contextlib import asynccontextmanager
from typing import Any

import aiosqlite

from db.factory import AsyncDatabaseFactory
from interfaces.db.base import IDatabaseManager
from schemas.supplier_schemas import ClothingCodeCreate, ClothingCodeUpdate


class ClothingCodesRepo:
    """Асинхронный репозиторий для работы с таблицей supplier_clothing_codes"""

    def __init__(self, conn_: aiosqlite.Connection | None = None):
        self._conn: aiosqlite.Connection | None = conn_
        self._db_manager: IDatabaseManager | None = None

    async def _get_db_manager(self) -> IDatabaseManager:
        """Lazy initialization of database manager."""
        if self._db_manager is None:
            self._db_manager = await AsyncDatabaseFactory.get_manager()
        return self._db_manager

    async def _get_connection(self) -> aiosqlite.Connection:
        """Получить соединение с БД (создать если нет)"""
        if self._conn is None:
            db_manager = await self._get_db_manager()
            # Получаем соединение через контекстный менеджер
            self._conn = await db_manager.get_db_dependency().__anext__()
        return self._conn

    @property
    def conn(self) -> aiosqlite.Connection | None:
        """Свойство для доступа к соединению (может быть None)"""
        return self._conn

    @asynccontextmanager
    async def get_connection(self):
        """Контекстный менеджер для получения соединения"""
        db_manager = await self._get_db_manager()
        async with db_manager.get_connection() as conn:
            yield conn

    async def close(self) -> None:
        """Закрыть соединение"""
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self):
        """Вход в контекстный менеджер"""
        await self._get_connection()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Выход из контекстного менеджера"""
        await self.close()

    async def _row_to_dict(self, row: aiosqlite.Row) -> dict[str, Any]:
        """Конвертировать aiosqlite.Row в словарь"""
        return dict(row)

    async def _execute_and_fetch_all(
        self, query: str, params: tuple[Any, ...] = ()
    ) -> list[dict[str, Any]]:
        """Выполнить запрос и вернуть все результаты"""
        async with self.get_connection() as conn:
            async with conn.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def _execute_and_fetch_one(
        self, query: str, params: tuple[Any, ... ] = ()
    ) -> dict[str, Any] | None:
        """Выполнить запрос и вернуть один результат"""
        async with self.get_connection() as conn:
            async with conn.execute(query, params) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def _execute(
        self, query: str, params: tuple[Any, ...] = ()
    ) -> aiosqlite.Cursor:
        """Выполнить запрос без возврата данных"""
        async with self.get_connection() as conn:
            return await conn.execute(query, params)

    # ----------------------------------------------------------------------
    # Основные CRUD операции
    # ----------------------------------------------------------------------

    async def get_all(
        self,
        supplier_id: int | None = None,
        skip: int = 0,
        limit: int = 1000,
        order_by: str = "id",
        order_dir: str = "ASC"
    ) -> list[dict[str, Any]]:
        """Получить все записи с фильтрацией по поставщику"""
        query = "SELECT * FROM supplier_clothing_codes"
        params: list[Any] = []

        if supplier_id:
            query += " WHERE supplier_id = ?"
            params.append(supplier_id)

        query += f" ORDER BY {order_by} {order_dir} LIMIT ? OFFSET ?"
        params.extend([limit, skip])

        return await self._execute_and_fetch_all(query, tuple(params))

    async def get_by_id(self, product_id: int) -> dict[str, Any] | None:
        """Получить запись по ID"""
        return await self._execute_and_fetch_one(
            "SELECT * FROM supplier_clothing_codes WHERE id = ?",
            (product_id,)
        )

    async def get_by_supplier_code(
        self,
        supplier_id: int,
        code: int
    ) -> dict[str, Any] | None:
        """Получить запись по коду поставщика"""
        return await self._execute_and_fetch_one(
            "SELECT * FROM supplier_clothing_codes WHERE supplier_id = ? AND code = ?",
            (supplier_id, code)
        )

    async def get_by_supplier_codes(
        self,
        supplier_id: int,
        codes: list[int],
    ) -> list[dict[str, Any]]:
        """Получить несколько записей по списку кодов"""
        if not codes:
            return []

        placeholders = ','.join(['?'] * len(codes))
        query = (
            "SELECT * FROM supplier_clothing_codes WHERE supplier_id = ? "
            f"AND code IN ({placeholders})"
        )
        params = [supplier_id] + codes

        return await self._execute_and_fetch_all(query, tuple(params))

    async def create(self, data: ClothingCodeCreate) -> int:
        """Создать запись, вернуть ID"""
        query = """
            INSERT INTO supplier_clothing_codes (
                code, name, category, subcategory, supplier_id,
                product_summary, size, color, supplier_code, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        values = (
            data.code, data.name, data.category, data.subcategory, data.supplier_id,
            data.product_summary, data.size, data.color, data.supplier_code, data.description
        )

        cursor = await self._execute(query, values)
        return cursor.lastrowid

    async def create_bulk(self, items: list[ClothingCodeCreate]) -> int:
        """Массовое создание записей"""
        if not items:
            return 0

        query = """
            INSERT INTO supplier_clothing_codes (
                code, name, category, subcategory, supplier_id,
                product_summary, size, color, supplier_code, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        values_list: list[tuple[Any, ...]] = []
        for item in items:
            values_list.append((
                item.code, item.name, item.category, item.subcategory, item.supplier_id,
                item.product_summary, item.size, item.color, item.supplier_code, item.description
            ))
        conn = await self._get_connection()
        cursor = await conn.executemany(query, values_list)
        return cursor.rowcount

    async def update(self, product_id: int, data: ClothingCodeUpdate) -> bool:
        """Обновить запись"""
        # Получаем только переданные поля
        update_data = data.model_dump(exclude_unset=True, exclude_none=True)

        if not update_data:
            return True

        # Формируем SET часть запроса
        set_clause = ", ".join([f"{key} = ?" for key in update_data.keys()])

        values = list(update_data.values())
        values.append(product_id)  # для WHERE

        query = f"UPDATE supplier_clothing_codes SET {set_clause} WHERE id = ?"

        cursor = await self._execute(query, tuple(values))
        return cursor.rowcount > 0

    async def delete(self, product_id: int) -> bool:
        """Удалить запись"""
        cursor = await self._execute(
            "DELETE FROM supplier_clothing_codes WHERE id = ?",
            (product_id,)
        )
        return cursor.rowcount > 0

    async def delete_all_by_supplier(self, supplier_id: int) -> int:
        """Удалить все записи поставщика"""
        cursor = await self._execute(
            "DELETE FROM supplier_clothing_codes WHERE supplier_id = ?",
            (supplier_id,)
        )
        return cursor.rowcount

    async def delete_all(self) -> int:
        """Удалить все записи"""
        cursor = await self._execute("DELETE FROM supplier_clothing_codes")
        return cursor.rowcount

    async def count(self, supplier_id: int | None = None) -> int:
        """Подсчитать количество записей"""
        query = "SELECT COUNT(*) as count FROM supplier_clothing_codes"
        params: list[Any] = []

        if supplier_id:
            query += " WHERE supplier_id = ?"
            params.append(supplier_id)

        result = await self._execute_and_fetch_one(query, tuple(params))
        return result['count'] if result else 0

    # ----------------------------------------------------------------------
    # Бизнес-логика
    # ----------------------------------------------------------------------

    async def upsert(self, data: ClothingCodeCreate) -> dict[str, Any]:
        """
        Вставить или обновить запись (upsert)
        Возвращает: {"action": "created/updated", "id": id}
        """
        # Проверяем существование
        existing = await self.get_by_supplier_code(data.supplier_id, data.code)

        if existing:
            # Обновляем
            update_data = ClothingCodeUpdate(**data.model_dump())
            await self.update(existing['id'], update_data)
            return {"action": "updated", "id": existing['id']}
        else:
            # Создаем
            new_id = await self.create(data)
            return {"action": "created", "id": new_id}

    async def upsert_bulk(
        self,
        items: list[ClothingCodeCreate]
    ) -> tuple[int, int, list[dict[str, Any]]]:
        """
        Массовый upsert
        Возвращает: (created_count, updated_count, errors)
        """
        created = 0
        updated = 0
        errors: list[Any] = []

        for idx, item in enumerate(items):
            try:
                result = await self.upsert(item)
                if result["action"] == "created":
                    created += 1
                else:
                    updated += 1
            except Exception as e:
                errors.append({
                    "row": idx,
                    "data": item.model_dump(),
                    "error": str(e)
                })

        return created, updated, errors

    async def get_by_filters(
        self,
        filters: dict[str, Any],
        skip: int = 0,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Получить записи по произвольным фильтрам"""
        where_clauses: list[str] = []
        params: list[Any] = []

        for key, value in filters.items():
            if value is not None:
                if isinstance(value, (list, tuple)):
                    # IN оператор
                    placeholders = ','.join(['?'] * len(value))
                    where_clauses.append(f"{key} IN ({placeholders})")
                    params.extend(value)
                else:
                    where_clauses.append(f"{key} = ?")
                    params.append(value)

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        query = f"SELECT * FROM supplier_clothing_codes WHERE {where_sql} ORDER BY id LIMIT ? OFFSET ?"
        params.extend([limit, skip])

        return await self._execute_and_fetch_all(query, tuple(params))

    async def search(
        self,
        search_term: str,
        fields: list[str] = ['name', 'code', 'supplier_code', 'description'],
        supplier_id: int | None = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """Полнотекстовый поиск"""
        if not search_term:
            return []

        like_term = f"%{search_term}%"
        where_conditions = [f"{field} LIKE ?" for field in fields]
        where_sql = " OR ".join(where_conditions)

        params: list[Any] = [like_term] * len(fields)

        if supplier_id:
            where_sql = f"({where_sql}) AND supplier_id = ?"
            params.append(supplier_id)

        query = (
            f"SELECT * FROM supplier_clothing_codes WHERE {where_sql} "
            "ORDER BY id LIMIT ?"
        )
        params.append(limit)

        return await self._execute_and_fetch_all(query, tuple(params))

    async def get_distinct_suppliers(self) -> list[int]:
        """Получить список всех уникальных ID поставщиков"""
        result = await self._execute_and_fetch_all(
            "SELECT DISTINCT supplier_id FROM supplier_clothing_codes "
            "ORDER BY supplier_id"
        )
        return [row['supplier_id'] for row in result]

    async def get_statistics(self, supplier_id: int | None = None) -> dict[str, Any]:
        """Получить расширенную статистику"""
        base_query = "FROM supplier_clothing_codes"
        params: list[Any] = []

        if supplier_id:
            base_query += " WHERE supplier_id = ?"
            params.append(supplier_id)

        # Общее количество
        count_query = f"SELECT COUNT(*) as count {base_query}"
        count_result = await self._execute_and_fetch_one(count_query, tuple(params))
        total = count_result['count'] if count_result else 0

        # Количество с размерами
        size_query = f"SELECT COUNT(*) as count {base_query} AND size IS NOT NULL AND size != ''"
        size_result = await self._execute_and_fetch_one(size_query, tuple(params))
        with_size = size_result['count'] if size_result else 0

        # Количество с цветами
        color_query = f"SELECT COUNT(*) as count {base_query} AND color IS NOT NULL AND color != ''"
        color_result = await self._execute_and_fetch_one(color_query, tuple(params))
        with_color = color_result['count'] if color_result else 0

        # Последние обновления
        recent_query = f"""
            SELECT created_at, updated_at {base_query}
            ORDER BY updated_at DESC LIMIT 1
        """
        recent_result = await self._execute_and_fetch_one(recent_query, tuple(params))

        return {
            "supplier_id": supplier_id,
            "total_records": total,
            "with_size": with_size,
            "with_color": with_color,
            "without_size": total - with_size,
            "without_color": total - with_color,
            "last_updated": recent_result['updated_at'] if recent_result else None,
            "last_created": recent_result['created_at'] if recent_result else None
        }


def get_clothing_code_repo() -> ClothingCodesRepo:
    return ClothingCodesRepo()
