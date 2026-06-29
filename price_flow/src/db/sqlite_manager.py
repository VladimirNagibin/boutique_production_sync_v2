"""Async SQLite database manager implementation."""

import asyncio
import sqlite3

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import aiosqlite

from core.logger import logger
from core.settings import settings
from interfaces.db.base import IDatabaseManager, ITransactionManager

from .sql_scripts import sql_script_create_table


class SQLiteTransactionManager(ITransactionManager):
    """Async SQLite transaction manager."""

    def __init__(self, connection: aiosqlite.Connection):
        self.connection = connection

    async def begin_transaction(self) -> None:
        """Begin a new transaction asynchronously."""
        await self.connection.execute("BEGIN TRANSACTION")

    async def commit(self) -> None:
        """Commit the current transaction asynchronously."""
        await self.connection.commit()

    async def rollback(self) -> None:
        """Rollback the current transaction asynchronously."""
        await self.connection.rollback()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        try:
            await self.begin_transaction()
            yield
            await self.commit()
        except Exception:
            await self.rollback()
            raise


class SQLiteManager(IDatabaseManager):
    """Async SQLite database manager."""

    def __init__(self, db_path: str = str(settings.DB_SQLITE_PATH), **kwargs: Any):
        self.db_path = db_path
        self.pool_size = kwargs.get("pool_size", settings.POOL_SIZE)
        self._connection_pool = None

    async def initialize(self) -> None:
        """Initialize database and connection pool."""
        await self._init_database()

    async def get_db_connection(self) -> aiosqlite.Connection:
        """Получить асинхронное соединение с SQLite"""
        conn = await aiosqlite.connect(str(self.db_path))
        conn.row_factory = aiosqlite.Row  # Возвращать строки как словари

        return conn

    @asynccontextmanager
    async def get_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Async context manager for database connections."""
        # logger.info(f"Initializing SQLite database at {self.db_path}")
        conn = await self.get_db_connection()

        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise
        finally:
            await conn.close()

    async def get_db_dependency(self) -> AsyncGenerator[aiosqlite.Connection]:
        """Dependency для FastAPI"""
        async with self.get_connection() as conn:
            yield conn

    async def _init_database(self) -> None:
        """Initialize database tables asynchronously."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

        async with self.get_connection() as conn:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await conn.executescript(sql_script_create_table)

            await conn.commit()
            logger.info("SQLite database initialized asynchronously")

    async def execute_query(
        self, query: str, params: tuple[Any] | None = None
    ) -> list[Any]:
        """Execute raw SQL query asynchronously."""
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params or ())
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows]

    async def execute_query_(
        self, query: str, params: tuple[Any] | None = None
    ) -> list[Any]:
        """Execute raw SQL query asynchronously."""
        async with self.get_connection() as conn:
            cursor = await conn.execute(query, params or ())
            rows = await cursor.fetchall()
            await cursor.close()
            return [dict(row) for row in rows]

    async def execute_many(self, query: str, params_list: list[Any]) -> None:
        """Execute many SQL statements asynchronously."""
        async with self.get_connection() as conn:
            await conn.executemany(query, params_list)
            await conn.commit()

    async def backup(self, backup_path: str | None = None) -> bool:
        """Create database backup using native SQLite API (thread-safe)."""
        backup_path = backup_path or f"{self.db_path}.backup"

        try:

            def _run_backup() -> None:
                src = sqlite3.connect(self.db_path)
                dst = sqlite3.connect(backup_path)
                src.backup(dst)
                dst.close()
                src.close()

            await asyncio.to_thread(_run_backup)
        except (OSError, sqlite3.Error) as e:
            logger.error(f"Backup failed: {e}")
            with suppress(OSError):
                Path(backup_path).unlink()
            return False
        else:
            logger.info(f"SQLite database backed up to {backup_path}")
            return True

    async def health_check(self) -> bool:
        """Check database health asynchronously."""
        try:
            async with self.get_connection() as conn:
                cursor = await conn.execute("SELECT 1")
                await cursor.fetchone()
                await cursor.close()
                return True
        except sqlite3.Error as e:
            logger.error(f"Health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close all connections asynchronously."""
        # Для SQLite aiosqlite соединения закрываются автоматически

    def create_transaction_manager(
        self, connection: aiosqlite.Connection
    ) -> SQLiteTransactionManager:
        """Create transaction manager for a connection."""
        return SQLiteTransactionManager(connection)

    async def add_column_to_table(
        self,
        table_name: str | None = None,
        column_def: str | None = None,
    ):
        """
        Добавляет колонку к существующей таблице

        Args:
            table_name: имя таблицы
            column_def: определение колонки (например: "new_column TEXT DEFAULT ''")
        """
        table_name = table_name or "supplier_clothing_codes"
        column_def = column_def or "supplier_code"

        # sql = f"ALTER TABLE {table_name} DROP COLUMN {column_def}"
        sql = f"ALTER TABLE {table_name} ADD COLUMN description TEXT DEFAULT ''"
        async with self.get_connection() as conn:
            await conn.execute(sql)
            await conn.commit()
            logger.info(f"SQLite add column: {column_def} to table: {table_name}")
