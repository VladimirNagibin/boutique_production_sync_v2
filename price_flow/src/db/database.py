
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import aiosqlite

from core.settings import settings

from .sql_scripts import sql_script_create_table


async def get_db_connection() -> aiosqlite.Connection:
    """Получить асинхронное соединение с SQLite"""
    conn = await aiosqlite.connect(settings.DB_SQLITE_PATH)
    conn.row_factory = aiosqlite.Row  # Возвращать строки как словари

    return conn

@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection]:
    """Асинхронный контекстный менеджер для работы с БД"""
    conn = await get_db_connection()
    try:
        yield conn
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    finally:
        await conn.close()

async def get_db_dependency() -> AsyncGenerator[aiosqlite.Connection]:
    """Dependency для FastAPI"""
    async with get_db() as conn:
        yield conn

async def init_db():
    """Инициализация базы данных"""
    async with get_db() as conn:
        await conn.execute("PRAGMA foreign_keys = ON")  # Включить внешние ключи
        await conn.execute("PRAGMA journal_mode = WAL")  # Режим WAL для конкурентности
        await conn.executescript(sql_script_create_table)
        await conn.commit()
