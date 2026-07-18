import abc
from functools import lru_cache
from typing import Any

from tinydb import TinyDB, Query  # type: ignore[import-not-found]

from core.settings import settings


class BaseStorage(abc.ABC):
    """Абстрактное хранилище состояния."""

    @abc.abstractmethod
    def set_state(self, key: str, value: Any) -> bool:
        """Save the state for a specific key."""

    @abc.abstractmethod
    def get_state(self, key: str, default: Any = None) -> Any:
        """Get the state for a specific key."""


class TinyDBStorage(BaseStorage):
    """
    Implementation of a storage using TinyDB.
    Каждое состояние хранится как отдельный документ {"key": "...", "value": ...}
    """

    def __init__(self, file_path: str) -> None:
        # TinyDB сам создает файл, если его нет
        self.db = TinyDB(file_path)
        self.query = Query()

    def set_state(self, key: str, value: Any) -> bool:
        """Set the state for a key using upsert."""
        try:
            # upsert: если документ с таким ключом есть — обновит, если нет — создаст
            self.db.upsert({"key": key, "value": value}, self.query.key == key)
            return True
        except Exception:
            return False

    def get_state(self, key: str, default: Any = None) -> Any:
        """Get the state for a key."""
        try:
            # Ищем документ по ключу
            doc = self.db.get(self.query.key == key)
            return doc["value"] if doc else default
        except Exception:
            return default


class State:
    """Class for working with states."""

    # Теперь этот класс просто проксирует вызовы к хранилищу,
    # так как вся логика перенесена в TinyDBStorage для максимальной производительности.

    def __init__(self, storage: BaseStorage) -> None:
        self.storage = storage

    def set_state(self, key: str, value: Any) -> bool:
        """Set the state for a key."""
        return self.storage.set_state(key, value)

    def get_state(self, key: str, default: Any = None) -> Any:
        """Get the state for a key."""
        return self.storage.get_state(key, default)


@lru_cache()
def get_storage(path: str = f"data/storage/{settings.tiny_db_path}") -> State:
    return State(TinyDBStorage(path))
