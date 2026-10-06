"""Тесты модуля логирования common.logger."""

from __future__ import annotations

import io
import json
import logging
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
import requests
from requests.exceptions import ConnectionError as RequestsConnectionError

from common import logger as logger_module
from common.log_context import bind_class, bind_log_context, reset_log_context
from common.logger import (
    CallerInfoFilter,
    SafeExtraLogger,
    SeqClefFormatter,
    SeqJsonHandler,
    _build_logging_config,
    _parse_retry_after,
    create_json_formatter,
    escape_message_template,
    split_qualname,
)


# ===== Вспомогательные объекты =====
class _FakeResponse:
    """Минимальный ответ requests для тестов SeqJsonHandler."""

    def __init__(self, status_code: int, headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self.text = ""


class _RecordingEvent(threading.Event):
    """Event, который запоминает задержки ожидания и не ждёт."""

    def __init__(self) -> None:
        super().__init__()
        self.delays: list[float] = []

    def wait(self, timeout: float | None = None) -> bool:
        self.delays.append(timeout or 0.0)
        return self.is_set()


class _CapturedLogger:
    """Изолированный логгер с JSON-хендлером и CallerInfoFilter."""

    def __init__(self) -> None:
        self.stream = io.StringIO()
        handler = logging.StreamHandler(self.stream)
        handler.setFormatter(create_json_formatter())
        handler.addFilter(CallerInfoFilter("test_service", "test"))
        # Родитель-логгер с хендлером, запись идёт из дочернего через propagate:
        # именно этот сценарий ломался, когда фильтр висел на логгере.
        self.parent = SafeExtraLogger("captured")
        self.parent.addHandler(handler)
        self.logger = SafeExtraLogger("captured.child")
        self.logger.parent = self.parent

    def records(self) -> list[dict[str, Any]]:
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]

    def last(self) -> dict[str, Any]:
        return self.records()[-1]


class _PriceLoader:
    """Класс-пример для проверки class_name/method_name."""

    def __init__(self, log: logging.Logger) -> None:
        self._log = log

    def run(self) -> None:
        self._log.info("price loaded")


def _module_function(log: logging.Logger) -> None:
    log.info("module function")


@pytest.fixture
def captured() -> _CapturedLogger:
    return _CapturedLogger()


@pytest.fixture
def seq_handler(monkeypatch: pytest.MonkeyPatch) -> Iterator[SeqJsonHandler]:
    monkeypatch.setattr(logger_module, "_create_seq_internal_logger", _silent_logger)
    handler = SeqJsonHandler(server_url="http://seq.test")
    handler._closing = _RecordingEvent()
    yield handler
    handler.close()


def _silent_logger() -> logging.Logger:
    silent = logging.getLogger("test.seq.internal")
    silent.propagate = False
    silent.addHandler(logging.NullHandler())
    return silent


def _seq_event() -> str:
    return json.dumps({"Timestamp": "2026-01-01T00:00:00.000Z", "MessageTemplate": "m"})


# ===== Конфигурация =====
def test_console_handler_has_caller_info_filter() -> None:
    """Регрессия: фильтр должен висеть на хендлере, а не на root-логгере."""
    config = _build_logging_config("INFO", service_name="svc")

    assert config["handlers"]["console"]["filters"] == ["caller_info"]
    assert "filters" not in config["loggers"][""]
    assert config["filters"]["caller_info"]["service_name"] == "svc"


def test_uvicorn_loggers_use_json_console() -> None:
    config = _build_logging_config("INFO")

    assert config["loggers"]["uvicorn.access"]["handlers"] == ["console"]
    assert config["loggers"]["uvicorn.error"]["propagate"] is True
    assert set(config["formatters"]) == {"json"}


# ===== Обязательные поля =====
def test_record_from_child_logger_has_required_fields(
    captured: _CapturedLogger,
) -> None:
    _PriceLoader(captured.logger).run()

    record = captured.last()
    assert record["module_name"] == __file__
    assert record["class_name"] == "_PriceLoader"
    assert record["method_name"] == "run"
    assert record["name"] == "captured.child"
    assert record["levelname"] == "INFO"
    assert record["message"] == "price loaded"
    assert record["service"] == "test_service"
    assert record["environment"] == "test"


def test_asctime_is_iso8601_utc(captured: _CapturedLogger) -> None:
    captured.logger.info("time check")

    assert captured.last()["asctime"].endswith("+00:00")


def test_module_function_has_null_class_name(captured: _CapturedLogger) -> None:
    _module_function(captured.logger)

    record = captured.last()
    assert record["class_name"] is None
    assert record["method_name"] == "_module_function"


def test_bind_class_is_fallback_for_functions(captured: _CapturedLogger) -> None:
    loader = _PriceLoader(captured.logger)
    with bind_class(loader):
        _module_function(captured.logger)

    assert captured.last()["class_name"] == "_PriceLoader"


def test_explicit_class_name_wins(captured: _CapturedLogger) -> None:
    captured.logger.info("explicit", extra={"class_name": "CustomClass"})

    assert captured.last()["class_name"] == "CustomClass"


def test_uvicorn_color_message_is_skipped(captured: _CapturedLogger) -> None:
    captured.logger.info("started", extra={"color_message": "\x1b[36mstarted"})

    assert "color_message" not in captured.last()


def test_cyrillic_is_not_escaped(captured: _CapturedLogger) -> None:
    captured.logger.info("upload", extra={"file_name": "Прайс.xlsx"})

    assert "Прайс.xlsx" in captured.stream.getvalue()


@pytest.mark.parametrize(
    ("qualname", "expected"),
    [
        ("PriceLoader.run", ("PriceLoader", "run")),
        ("helper", (None, "helper")),
        ("<module>", (None, "<module>")),
        ("outer.<locals>.inner", (None, "inner")),
        ("factory.<locals>.Local.method", ("Local", "method")),
        ("", (None, "")),
    ],
)
def test_split_qualname(qualname: str, expected: tuple[str | None, str]) -> None:
    assert split_qualname(qualname) == expected


# ===== Корреляция =====
def test_request_and_run_ids_from_context(captured: _CapturedLogger) -> None:
    tokens = bind_log_context(request_id="req-1", run_id="run-1", job_name="job")
    try:
        captured.logger.info("with context")
    finally:
        reset_log_context(tokens)

    record = captured.last()
    assert record["request_id"] == "req-1"
    assert record["correlation_id"] == "req-1"
    assert record["run_id"] == "run-1"
    assert record["job_name"] == "job"


# ===== Маскирование =====
def test_secret_extra_is_redacted(captured: _CapturedLogger) -> None:
    captured.logger.info("auth", extra={"api_token": "abc", "supplier": "lanset"})

    record = captured.last()
    assert record["api_token"] == "[REDACTED]"
    assert record["supplier"] == "lanset"


def test_secret_in_message_args_is_redacted(captured: _CapturedLogger) -> None:
    captured.logger.info("fetch %s", "https://api.test/v1?token=SECRET")

    message = captured.last()["message"]
    assert "SECRET" not in message
    assert message == "fetch https://api.test/v1?redacted"


def test_filter_is_idempotent() -> None:
    log_filter = CallerInfoFilter("svc", "env")
    record = SafeExtraLogger("x").makeRecord(
        "x", logging.INFO, __file__, 1, "token=%s", ("abc",), None, func="A.run"
    )

    log_filter.filter(record)
    first = (record.getMessage(), record.__dict__.copy())
    log_filter.filter(record)

    assert (record.getMessage(), record.__dict__) == first
    assert record.getMessage() == "token=[REDACTED]"


# ===== Seq: форматтер =====
def test_seq_formatter_escapes_braces_and_skips_system_fields() -> None:
    record = SafeExtraLogger("x").makeRecord(
        "x", logging.INFO, __file__, 1, 'payload {"a": 1}', (), None, func="f"
    )

    event = json.loads(SeqClefFormatter().format(record))

    assert event["MessageTemplate"] == 'payload {{"a": 1}}'
    assert "taskName" not in event["Properties"]


def test_escape_message_template() -> None:
    assert escape_message_template("{x} and {{y}}") == "{{x}} and {{{{y}}}}"


# ===== Seq: отправка =====
def test_seq_retries_transient_errors(
    seq_handler: SeqJsonHandler, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = [_FakeResponse(503), _FakeResponse(429), _FakeResponse(201)]
    calls: list[dict[str, Any]] = []

    def fake_post(*args: Any, **kwargs: Any) -> _FakeResponse:
        calls.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr(requests, "post", fake_post)

    seq_handler._send_batch([_seq_event()])

    assert len(calls) == 3
    assert isinstance(seq_handler._closing, _RecordingEvent)
    # Экспоненциальная задержка: 0.5, затем 1.0.
    assert seq_handler._closing.delays == [0.5, 1.0]
    assert seq_handler._dropped_count == 0
    assert seq_handler._fail_count == 0


def test_seq_honors_retry_after(
    seq_handler: SeqJsonHandler, monkeypatch: pytest.MonkeyPatch
) -> None:
    responses = [_FakeResponse(429, {"Retry-After": "3"}), _FakeResponse(200)]
    monkeypatch.setattr(requests, "post", lambda *a, **k: responses.pop(0))

    seq_handler._send_batch([_seq_event()])

    assert isinstance(seq_handler._closing, _RecordingEvent)
    assert seq_handler._closing.delays == [3.0]


def test_seq_does_not_retry_client_errors(
    seq_handler: SeqJsonHandler, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def fake_post(*args: Any, **kwargs: Any) -> _FakeResponse:
        calls.append(1)
        return _FakeResponse(400)

    monkeypatch.setattr(requests, "post", fake_post)

    seq_handler._send_batch([_seq_event(), _seq_event()])

    assert len(calls) == 1
    assert seq_handler._dropped_count == 2


def test_seq_circuit_cooldown_grows_exponentially(
    seq_handler: SeqJsonHandler, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_post(*args: Any, **kwargs: Any) -> _FakeResponse:
        raise RequestsConnectionError("connection refused")

    monkeypatch.setattr(requests, "post", failing_post)
    monkeypatch.setattr(logger_module, "SEQ_MAX_RETRIES", 0)

    cooldowns: list[float] = []
    for _ in range(2):
        for _ in range(logger_module.SEQ_MAX_FAILURES):
            seq_handler._send_batch([_seq_event()])
        cooldowns.append(seq_handler._circuit_open_until - time.monotonic())
        # Имитируем истечение cooldown.
        seq_handler._circuit_open_until = 0.0

    base = logger_module.SEQ_CIRCUIT_COOLDOWN_SECONDS
    assert cooldowns[0] == pytest.approx(base, abs=1)
    assert cooldowns[1] == pytest.approx(base * 2, abs=1)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("5", 5.0), ("0", 0.0), ("-1", None), (None, None), ("Wed, 21 Oct", None)],
)
def test_parse_retry_after(value: str | None, expected: float | None) -> None:
    assert _parse_retry_after(value) == expected
