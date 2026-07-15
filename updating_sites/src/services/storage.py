import abc
import json
from functools import lru_cache
from typing import Any


class BaseStorage(abc.ABC):
    """Abstract state storage."""

    @abc.abstractmethod
    def save_state(self, state: dict[str, Any]) -> None:
        """Save the state to the storage."""

    @abc.abstractmethod
    def retrieve_state(self) -> dict[str, Any]:
        """Get the state from the storage."""


class JsonFileStorage(BaseStorage):
    """
    Implementation of a storage using a local file.
    Storage format: JSON
    """

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path

    def save_state(self, state: dict[str, Any]) -> None:
        """Save the state to the storage."""
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(state, f)

    def retrieve_state(self) -> dict[str, Any]:
        """Get the state from the storage."""
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            state = {}
        return state  # type: ignore[no-any-return]


class State:
    """Class for working with states."""

    def __init__(self, storage: BaseStorage) -> None:
        self.storage = storage

    def set_state(self, key: str, value: Any) -> bool:
        """Set the state for a key."""
        try:
            state = self.storage.retrieve_state()
            state[key] = value
            self.storage.save_state(state)
            return True
        except Exception:
            return False

    def get_state(self, key: str, default: Any = None) -> Any:
        """Get the state for a key."""
        try:
            state = self.storage.retrieve_state()
            return state.get(key, default)
        except Exception:
            return None


@lru_cache()
def get_storage(path: str = "data/storage/storage.json") -> State:
    return State(JsonFileStorage(path))
