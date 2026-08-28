"""
Модуль работы с SQLAlchemy (PostgreSQL).
"""

from __future__ import annotations

import asyncio
import time

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

import sqlalchemy as sa

from sqlalchemy import create_engine, event
from sqlalchemy.exc import DatabaseError as SQLAlchemyDatabaseError
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from common.exceptions.database import (
    DatabaseConnectionError,
    DatabaseError,
    DatabaseLoadError,
)
from core.logger import get_logger
from core.settings import settings


logger = get_logger(__name__)


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator, Callable

    from sqlalchemy import Engine
    from sqlalchemy.ext.asyncio import AsyncEngine


# ===== Константы / Constants =====
DEFAULT_POOL_SIZE = 20
DEFAULT_MAX_OVERFLOW = 10
ENGINE_COMMAND_TIMEOUT = 60  # seconds (for asyncpg)
ENGINE_STATEMENT_TIMEOUT = "30000"  # milliseconds (PostgreSQL)
SLOW_QUERY_THRESHOLD_MS = 1000.0
SLOW_QUERY_STATEMENT_MAX_LEN = 500


def _register_slow_query_logging(sync_engine: Engine) -> None:
    """Пишет WARNING, если SQL выполняется дольше порога."""

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn: Any,
        _cursor: Any,
        _statement: Any,
        _parameters: Any,
        _context: Any,
        _executemany: Any,
    ) -> None:
        conn.info["query_start_perf"] = time.perf_counter()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn: Any,
        _cursor: Any,
        statement: Any,
        _parameters: Any,
        _context: Any,
        _executemany: Any,
    ) -> None:
        started = conn.info.get("query_start_perf")
        if started is None:
            return
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if elapsed_ms < SLOW_QUERY_THRESHOLD_MS:
            return
        statement_text = str(statement) if statement else ""
        logger.warning(
            "Slow database query",
            extra={
                "duration_ms": round(elapsed_ms, 2),
                "threshold_ms": SLOW_QUERY_THRESHOLD_MS,
                "statement": statement_text[:SLOW_QUERY_STATEMENT_MAX_LEN],
            },
        )


# ===== Базовый класс моделей / Base Model =====
class Base(AsyncAttrs, DeclarativeBase):
    """
    Абстрактный базовый класс для всех моделей SQLAlchemy.
    """

    __abstract__ = True


# ===== Конфигурация базы данных / Database Configuration =====
class DatabaseConfig:
    """Конфигурация подключения к БД (DSN, пул, таймауты)."""

    def __init__(self) -> None:
        self.dsn: str = settings.dsn
        self.echo: bool = settings.database.echo
        self.pool_size: int = DEFAULT_POOL_SIZE
        self.max_overflow: int = DEFAULT_MAX_OVERFLOW
        self.pool_pre_ping: bool = True
        self.future: bool = True

    def is_postgres(self) -> bool:
        """Проверяет, используется ли PostgreSQL."""
        return "postgresql" in self.dsn

    @property
    def sync_dsn(self) -> str:
        """
        Формирует DSN для синхронного подключения.
        Заменяет асинхронный драйвер (asyncpg) на синхронный (psycopg2).
        """
        if "postgresql+asyncpg" in self.dsn:
            return self.dsn.replace(
                "postgresql+asyncpg", "postgresql+psycopg2"
            )
        if self.dsn.startswith("postgresql://"):
            return self.dsn.replace(
                "postgresql://", "postgresql+psycopg2://", 1
            )
        return self.dsn

    def build_connect_args(self) -> dict[str, Any]:
        """
        Формирует аргументы для подключения в зависимости от типа БД.
        """
        if self.is_postgres():
            return {
                "command_timeout": ENGINE_COMMAND_TIMEOUT,
                "server_settings": {
                    "jit": "off",  # Отключаем JIT для уменьшения задержек
                    "statement_timeout": ENGINE_STATEMENT_TIMEOUT,
                },
            }
        return {}

    def build_sync_connect_args(self) -> dict[str, Any]:
        """Формирует аргументы для синхронного подключения (psycopg2)."""
        if self.is_postgres():
            return {
                "connect_timeout": 10,
                "options": f"-c statement_timeout={ENGINE_STATEMENT_TIMEOUT}",
            }
        return {}


# ===== Менеджер базы данных / Database Manager =====
class DatabaseManager:
    """
    Менеджер жизненного цикла подключения к БД.
    Управляет асинхронным и синхронным движками (Engine) и фабрикой сессий.
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._engine: AsyncEngine | None = None
        self._sync_engine: Engine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        """
        Инициализирует движок и фабрику сессий.

        Raises:
            DatabaseConnectionError: Если не удалось подключиться к БД.
            DatabaseError: При ошибках конфигурации движка.
        """
        if self._initialized:
            logger.warning("Database manager is already initialized")
            return

        logger.info(
            "Initializing database manager",
            extra={
                "pool_size": self._config.pool_size,
                "max_overflow": self._config.max_overflow,
                "is_postgres": self._config.is_postgres(),
            },
        )
        try:
            self._create_engines()
            await self._test_connection()
            self._create_session_factory()
            self._initialized = True
            logger.info(
                "Database manager initialized",
                extra={"is_postgres": self._config.is_postgres()},
            )
        except OperationalError as e:
            logger.error(
                "Database connection failed",
                extra={"error_type": type(e).__name__},
                exc_info=True,
            )
            raise DatabaseConnectionError(
                message="Cannot connect to database",
                details={"error": str(e)},
            ) from e
        except SQLAlchemyError as e:
            logger.error(
                "Database engine initialization failed",
                extra={"error_type": type(e).__name__},
                exc_info=True,
            )
            raise DatabaseError(
                message="Database engine initialization failed",
                details={"error": str(e)},
            ) from e
        except Exception as e:
            logger.error(
                "Unexpected database initialization error",
                extra={"error_type": type(e).__name__},
                exc_info=True,
            )
            raise DatabaseError(
                message="Unexpected database initialization error",
                details={"error": str(e)},
            ) from e

    def _create_engines(self) -> None:
        """Создаёт асинхронный и синхронный движки."""
        # 1. Асинхронный движок для ORM и стандартных запросов
        self._engine = create_async_engine(
            self._config.dsn,
            echo=self._config.echo,
            future=self._config.future,
            pool_pre_ping=self._config.pool_pre_ping,
            pool_size=self._config.pool_size,
            max_overflow=self._config.max_overflow,
            connect_args=self._config.build_connect_args(),
        )

        # 2. Синхронный движок для тяжелых блокирующих операций
        # (Pandas, CSV export)
        self._sync_engine = create_engine(
            self._config.sync_dsn,
            echo=self._config.echo,
            pool_pre_ping=self._config.pool_pre_ping,
            pool_size=self._config.pool_size,
            max_overflow=self._config.max_overflow,
            connect_args=self._config.build_sync_connect_args(),
        )
        _register_slow_query_logging(self._engine.sync_engine)
        _register_slow_query_logging(self._sync_engine)

    async def _test_connection(self) -> None:
        """
        Проверяет соединение путём выполнения простого запроса.

        Raises:
            DatabaseConnectionError: Если тестовый запрос не удался.
        """
        if self._engine is None:
            raise DatabaseError(message="Engine not created")
        try:
            async with self._engine.connect() as conn:
                await conn.execute(sa.text("SELECT 1"))
        except OperationalError as e:
            raise DatabaseConnectionError(
                message="Connection test failed (SELECT 1)",
                details={"error": str(e)},
            ) from e
        except SQLAlchemyError as e:
            raise DatabaseError(
                message=f"Connection test error: {e}",
                details={"error": str(e)},
            ) from e

    def _create_session_factory(self) -> None:
        """Создаёт фабрику асинхронных сессий."""
        if self._engine is None:
            raise DatabaseError(message="Engine not created")
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        """
        Возвращает экземпляр движка БД.

        Raises:
            DatabaseError: Если движок не был инициализирован.
        """
        if not self._initialized or self._engine is None:
            raise DatabaseError(
                message="Database not initialized. Call initialize() first."
            )
        return self._engine

    @property
    def sync_engine(self) -> Engine:
        """
        Возвращает экземпляр синхронного движка БД.
        Используется для выполнения блокирующих операций в отдельных потоках
        (asyncio.to_thread).
        """
        if not self._initialized or self._sync_engine is None:
            raise DatabaseError(
                message="Database not initialized. Call initialize() first."
            )
        return self._sync_engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """
        Возвращает фабрику сессий.

        Raises:
            DatabaseError: Если менеджер не был инициализирован.
        """
        if not self._initialized or self._session_factory is None:
            raise DatabaseError(
                message="Database not initialized. Call initialize() first."
            )
        return self._session_factory

    async def dispose(self) -> None:
        """Корректно закрывает все соединения и освобождает ресурсы."""
        if not self._initialized:
            return

        logger.info("Closing database manager")
        try:
            if self._engine is not None:
                await self._engine.dispose()
            if self._sync_engine is not None:
                self._sync_engine.dispose()
        except SQLAlchemyError as e:
            logger.error(
                "Failed to close database engine",
                extra={"error_type": type(e).__name__},
                exc_info=True,
            )
        finally:
            self._initialized = False
            self._engine = None
            self._sync_engine = None
            self._session_factory = None
            logger.info("Database manager closed")


# ===== Глобальный экземпляр менеджера =====
_db_config = DatabaseConfig()
db_manager = DatabaseManager(_db_config)


# ===== Управление схемами (Создание/Удаление таблиц)/Schema Management =====
async def _run_schema_sync_action(action: str) -> None:
    """
    Вспомогательная функция для выполнения синхронных действий над схемой
    (create_all/drop_all) в асинхронном контексте.

    Args:
        action: Название метода для вызова ('create_all' или 'drop_all').

    Raises:
        DatabaseLoadError: При ошибке выполнения операции над схемой.
    """
    try:
        engine_instance = db_manager.engine
        async with engine_instance.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: getattr(Base.metadata, action)(sync_conn)
            )
        logger.info(
            "Database schema action completed",
            extra={"schema_action": action},
        )
    except SQLAlchemyError as e:
        logger.error(
            "Database schema action failed",
            extra={"schema_action": action, "error_type": type(e).__name__},
            exc_info=True,
        )
        raise DatabaseLoadError(
            message=f"Schema action '{action}' failed",
            details={"original_error": str(e)},
        ) from e
    except Exception as e:
        logger.error(
            "Unexpected database schema action error",
            extra={"schema_action": action, "error_type": type(e).__name__},
            exc_info=True,
        )
        raise DatabaseLoadError(
            message=f"Unexpected error during schema action '{action}'",
            details={"original_error": str(e)},
        ) from e


async def create_database_tables() -> None:
    """Создаёт все таблицы в БД, используя метаданные моделей."""
    await _run_schema_sync_action("create_all")


async def drop_database_tables() -> None:
    """Удаляет все таблицы из БД."""
    await _run_schema_sync_action("drop_all")


# ===== Контекстный менеджер сессии / Session Context Manager =====
@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """
    Предоставляет асинхронную сессию SQLAlchemy.

    Управляет транзакцией: COMMIT при успехе, ROLLBACK при ошибке.
    Гарантирует закрытие сессии при выходе из контекста.

    Usage:
        async with get_session() as session:
            await session.execute(...)

    Raises:
        DatabaseConnectionError: При проблемах с сетью/подключением.
        DatabaseLoadError: При ошибках целостности данных.
        DatabaseError: При прочих ошибках БД.
    """
    session: AsyncSession = db_manager.session_factory()
    try:
        yield session
        await session.commit()
    except OperationalError as e:
        await session.rollback()
        logger.error(
            "Database session rolled back after connection error",
            extra={"error_type": type(e).__name__},
            exc_info=True,
        )
        raise DatabaseConnectionError(
            message="Database connection lost during operation",
            details={"original_error": str(e)},
        ) from e
    except IntegrityError as e:
        await session.rollback()
        logger.error(
            "Database session rolled back after integrity error",
            extra={"error_type": type(e).__name__},
            exc_info=True,
        )
        raise DatabaseLoadError(
            message="Data integrity constraint violated",
            details={"original_error": str(e)},
        ) from e
    except SQLAlchemyDatabaseError as e:
        await session.rollback()
        logger.error(
            "Database session rolled back after execution error",
            extra={"error_type": type(e).__name__},
            exc_info=True,
        )
        raise DatabaseError(
            message="Database operation failed",
            details={"original_error": str(e)},
        ) from e
    except Exception as e:
        await session.rollback()
        logger.error(
            "Database session rolled back after unexpected error",
            extra={"error_type": type(e).__name__},
            exc_info=True,
        )
        raise DatabaseError(
            message="Unexpected database error",
            details={"original_error": str(e)},
        ) from e
    finally:
        await session.close()


async def get_session_generator() -> AsyncGenerator[AsyncSession]:
    """
    Генератор сессий для использования в зависимости FastAPI (Depends).

    Usage:
        @app.get("/")
        async def endpoint(
            session: AsyncSession = Depends(get_session_generator)
        ):
            ...
    """
    async with get_session() as session:
        yield session


# ===== Утилиты для синхронных операций / Sync Operations Utilities =====
async def run_sync_db_operation[T](
    sync_func: Callable[..., T], *args: Any, **kwargs: Any
) -> T:
    """
    Выполняет блокирующую функцию, работающую с БД (например, pandas.to_sql),
    в отдельном потоке, чтобы не блокировать event loop FastAPI.

    Автоматически передает синхронный движок первым аргументом, если функция
    его ожидает.

    Usage:
        def _load_data(sync_engine: Engine, file_path: Path):
            df = pd.read_csv(file_path)
            df.to_sql("table", sync_engine, if_exists="append")

        await run_sync_db_operation(_load_data, file_path)
    """
    import inspect

    sig = inspect.signature(sync_func)

    # Если функция принимает 'sync_engine' или 'engine' как первый параметр,
    # передаем его
    params = list(sig.parameters.keys())
    if params and params[0] in ("sync_engine", "engine", "conn"):
        return await asyncio.to_thread(
            sync_func, db_manager.sync_engine, *args, **kwargs
        )

    return await asyncio.to_thread(sync_func, *args, **kwargs)


# ===== Мониторинг здоровья / Health Check =====
class DatabaseHealthCheck:
    """Утилиты для мониторинга состояния базы данных."""

    @staticmethod
    async def is_healthy() -> bool:
        """Проверяет, отвечает ли БД на простой запрос."""
        try:
            engine = db_manager.engine
            async with engine.connect() as conn:
                await conn.execute(sa.text("SELECT 1"))
        except (OperationalError, SQLAlchemyError, DatabaseError) as e:
            logger.exception(
                "Database health check failed",
                extra={"error_type": type(e).__name__},
            )
            return False
        except Exception as e:
            logger.error(
                "Unexpected database health check error",
                extra={"error_type": type(e).__name__},
                exc_info=True,
            )
            return False
        else:
            return True

    @staticmethod
    async def get_connection_info() -> dict[str, Any]:
        """Возвращает информацию о настройках подключения."""
        return {
            "dsn": _db_config.dsn,
            "sync_dsn": _db_config.sync_dsn,
            "pool_size": _db_config.pool_size,
            "max_overflow": _db_config.max_overflow,
            "echo": _db_config.echo,
            "is_postgres": _db_config.is_postgres(),
        }


# Backward compatibility exports
# engine: AsyncEngine = db_manager.engine
# async_session: async_sessionmaker[AsyncSession] = db_manager.session_factory
