"""Abstract base classes defining async repository interfaces."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol, TypeVar
from uuid import UUID


T = TypeVar("T")
CreateSchema = TypeVar("CreateSchema", contravariant=True)
UpdateSchema = TypeVar("UpdateSchema", contravariant=True)


class IRepository(Protocol[T, CreateSchema, UpdateSchema]):
    """Abstract async base repository interface."""

    async def create(self, data: CreateSchema) -> T | None:
        """Create a new record asynchronously."""

    async def get_by_id(self, record_id: UUID) -> T | None:
        """Get record by ID asynchronously."""

    async def get_all(
        self, skip: int = 0, limit: int = 100, filters: dict[str, Any] | None = None
    ) -> list[T]:
        """Get all records with pagination and filtering asynchronously."""
        ...

    async def update(self, record_id: UUID, data: UpdateSchema) -> T | None:
        """Update a record asynchronously."""

    async def delete(self, record_id: UUID) -> bool:
        """Delete a record asynchronously."""
        ...

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """Count records with optional filtering asynchronously."""
        ...

    async def exists(self, record_id: UUID) -> bool:
        """Check if record exists asynchronously."""
        ...


class ITransactionManager(ABC):
    """Abstract interface for async transaction management."""

    @abstractmethod
    async def begin_transaction(self) -> None:
        """Begin a new transaction asynchronously."""

    @abstractmethod
    async def commit(self) -> None:
        """Commit the current transaction asynchronously."""

    @abstractmethod
    async def rollback(self) -> None:
        """Rollback the current transaction asynchronously."""

    @abstractmethod
    def transaction(self) -> AbstractAsyncContextManager[None]:
        """Async context manager for transactions."""
        ...


class IDatabaseManager(ABC):
    """Abstract async database manager interface."""

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize database and connection pool."""

    @abstractmethod
    def get_connection(self) -> AbstractAsyncContextManager[Any]:
        """Get database connection asynchronously."""
        ...

    @abstractmethod
    def get_db_dependency(self) -> AsyncGenerator[Any]:
        """Get database connection as FastAPI dependency."""
        ...

    @abstractmethod
    async def execute_query(
        self, query: str, params: tuple[Any, ...] | None = None
    ) -> list[Any]:
        """Execute raw SQL query asynchronously."""
        ...

    @abstractmethod
    async def execute_many(self, query: str, params_list: list[Any]) -> None:
        """Execute many SQL statements asynchronously."""

    @abstractmethod
    async def backup(self, backup_path: str) -> bool:
        """Create database backup asynchronously."""
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Check database health asynchronously."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close all connections asynchronously."""
