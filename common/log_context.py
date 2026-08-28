"""Контекст корреляции логов: request_id, run_id, class_name, job_name."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("log_request_id", default=None)
_run_id: ContextVar[str | None] = ContextVar("log_run_id", default=None)
_class_name: ContextVar[str | None] = ContextVar("log_class_name", default=None)
_job_name: ContextVar[str | None] = ContextVar("log_job_name", default=None)


class LogContextTokens:
    """Токены ContextVar для последующего reset."""

    def __init__(self) -> None:
        self._items: list[tuple[ContextVar[Any], Token[Any]]] = []

    def remember(self, var: ContextVar[Any], token: Token[Any]) -> None:
        self._items.append((var, token))

    def reset(self) -> None:
        for var, token in reversed(self._items):
            var.reset(token)
        self._items.clear()


def bind_log_context(
    *,
    request_id: str | None = None,
    run_id: str | None = None,
    class_name: str | None = None,
    job_name: str | None = None,
) -> LogContextTokens:
    """
    Записывает поля корреляции в контекст текущего потока/asyncio-задачи.

    Переданные None не меняют уже установленные значения.
    """
    tokens = LogContextTokens()
    if request_id is not None:
        tokens.remember(_request_id, _request_id.set(request_id))
    if run_id is not None:
        tokens.remember(_run_id, _run_id.set(run_id))
    if class_name is not None:
        tokens.remember(_class_name, _class_name.set(class_name))
    if job_name is not None:
        tokens.remember(_job_name, _job_name.set(job_name))
    return tokens


def reset_log_context(tokens: LogContextTokens) -> None:
    """Откатывает bind_log_context."""
    tokens.reset()


def get_request_id() -> str | None:
    """Возвращает request_id текущего запроса, если есть."""
    return _request_id.get()


def get_run_id() -> str | None:
    """Возвращает run_id фоновой задачи, если есть."""
    return _run_id.get()


def get_class_name() -> str | None:
    """Возвращает class_name из контекста."""
    return _class_name.get()


def get_job_name() -> str | None:
    """Возвращает имя фоновой задачи из контекста."""
    return _job_name.get()


def new_id() -> str:
    """Генерирует идентификатор корреляции."""
    return str(uuid.uuid4())


@contextmanager
def log_run(job_name: str, *, request_id: str | None = None) -> Iterator[str]:
    """
    Контекст одной фоновой задачи: новый run_id и имя job.

    Args:
        job_name: Имя задачи для Seq (например convert, clear_files).
        request_id: Сквозной id HTTP-запроса, если известен.

    Yields:
        Сгенерированный run_id.
    """
    run_id = new_id()
    tokens = bind_log_context(
        run_id=run_id,
        job_name=job_name,
        request_id=request_id,
    )
    try:
        yield run_id
    finally:
        reset_log_context(tokens)


@contextmanager
def bind_class(obj: object) -> Iterator[None]:
    """Пишет class_name в контекст логов на время вызова."""
    tokens = bind_log_context(class_name=type(obj).__name__)
    try:
        yield
    finally:
        reset_log_context(tokens)
