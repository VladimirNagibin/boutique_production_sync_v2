"""Модуль настройки логирования приложения.

Обеспечивает вывод логов в консоль (JSON),
файл с ротацией и удалённый сервер Seq.
Отправка в Seq выполняется в фоновом потоке через очередь,
чтобы не блокировать async event loop и не вызывать deadlock.
Добавляет в каждую запись путь модуля и имя функции
из стандартных полей LogRecord (pathname, funcName), без inspect.stack().
"""

from __future__ import annotations

import atexit
import json
import logging
import logging.config
import os
import queue
import sys
import threading
import time
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import requests
from pythonjsonlogger.json import JsonFormatter
from requests.exceptions import RequestException

from .log_context import (
    get_class_name,
    get_job_name,
    get_request_id,
    get_run_id,
)
from .log_redact import (
    is_safe_log_key,
    redact_key_value,
    redact_log_value,
    redact_text,
)
from .settings import AppSettings, SeqSettings, load_prefixed_settings
from .utils import FILTER_FIELDS, SYSTEM_FIELDS, LogLevel

# ===== Константы настройки =====
SEQ_BATCH_SIZE = 50
SEQ_AUTO_FLASH_INTERVAL = 2.0
SEQ_TIMEOUT = 5
SEQ_QUEUE_MAXSIZE = 2000
SEQ_MAX_FAILURES = 5
SEQ_CIRCUIT_COOLDOWN_SECONDS = 30.0
SEQ_WORKER_JOIN_TIMEOUT = 5.0
FILE_MAX_BYTES = 10 * 1024 * 1024
FILE_BACKUP_COUNT = 5
_SEQ_STOP = object()


def _create_seq_internal_logger() -> logging.Logger:
    """Создаёт изолированный логгер для ошибок Seq-handler.

    Не пропагирует в root, чтобы исключить рекурсию и deadlock
    при сбоях отправки в Seq.
    """
    internal_logger = logging.getLogger(f"{__name__}.SeqJsonHandler")
    internal_logger.propagate = False
    internal_logger.setLevel(logging.WARNING)
    if not internal_logger.handlers:
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )
        internal_logger.addHandler(stderr_handler)
    return internal_logger


# ===== Хендлер для асинхронной отправки в Seq =====
class SeqJsonHandler(logging.Handler):
    """Отправляет логи в Seq через HTTP API без блокировки вызывающего потока.

    ``emit`` только форматирует запись и кладёт её в очередь.
    Фоновый поток накапливает события и отправляет их пачками.
    Ошибки отправки пишутся во внутренний stderr-логгер без propagate.
    """

    def __init__(
        self,
        server_url: str,
        api_key: str = "",
        batch_size: int = SEQ_BATCH_SIZE,
        auto_flush_interval: float = SEQ_AUTO_FLASH_INTERVAL,
        queue_maxsize: int = SEQ_QUEUE_MAXSIZE,
    ) -> None:
        """Инициализирует хендлер.

        Args:
            server_url: Базовый URL сервера Seq (например, http://seq:80).
            api_key: API-ключ для аутентификации (опционально).
            batch_size: Количество событий в одной пачке.
            auto_flush_interval: Максимальное время (сек) между
                автоматическими отправками.
            queue_maxsize: Максимальный размер очереди событий.
        """
        super().__init__()
        self.server_url = server_url.rstrip("/")
        self.api_key = api_key
        self.batch_size = max(1, batch_size)
        self.auto_flush_interval = auto_flush_interval
        self._queue: queue.Queue[str | object] = queue.Queue(maxsize=queue_maxsize)
        self._logger = _create_seq_internal_logger()
        self._fail_count = 0
        self._circuit_open_until = 0.0
        self._dropped_count = 0
        self._closed = False
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="seq-log-sender",
            daemon=True,
        )
        self._worker.start()

    # ----- Публичные методы -----

    def emit(self, record: logging.LogRecord) -> None:
        """Форматирует запись и ставит её в очередь без сетевого I/O."""
        if self._closed:
            return
        try:
            if time.time() < self._circuit_open_until:
                self._dropped_count += 1
                return
            msg = self.format(record)
            self._queue.put_nowait(msg)
        except queue.Full:
            self._dropped_count += 1
            if self._dropped_count == 1 or self._dropped_count % 100 == 0:
                self._logger.warning(
                    "Seq queue full, dropped %d events",
                    self._dropped_count,
                )
        except (ValueError, TypeError, AttributeError) as e:
            self._logger.error("Error formatting record: %s", e, exc_info=True)
            self.handleError(record)
        except Exception as e:
            self._logger.error(
                "Unexpected error formatting record: %s",
                e,
                exc_info=True,
            )
            self.handleError(record)

    def flush(self) -> None:
        """Дожидается опустошения очереди (без остановки воркера)."""
        if self._closed:
            return
        # Воркер сам отправит накопленное по интервалу/размеру.
        # Здесь ждём, пока очередь опустеет, с таймаутом.
        deadline = time.time() + SEQ_WORKER_JOIN_TIMEOUT
        while not self._queue.empty() and time.time() < deadline:
            time.sleep(0.05)

    def close(self) -> None:
        """Останавливает воркер и отправляет оставшиеся события."""
        if self._closed:
            super().close()
            return
        self._closed = True
        try:
            try:
                self._queue.put(_SEQ_STOP, timeout=1.0)
            except queue.Full:
                self._logger.warning("Seq queue full during close, stop signal skipped")
            self._worker.join(timeout=SEQ_WORKER_JOIN_TIMEOUT)
            if self._worker.is_alive():
                self._logger.warning("Seq worker did not stop in time")
            if self._dropped_count:
                self._logger.warning(
                    "Seq handler closed with %d dropped events",
                    self._dropped_count,
                )
        finally:
            super().close()

    # ----- Приватные методы -----

    def _worker_loop(self) -> None:
        """Фоновый цикл: накопление батча и отправка в Seq."""
        batch: list[str] = []
        last_flush = time.time()
        while True:
            timeout = max(0.05, self.auto_flush_interval - (time.time() - last_flush))
            try:
                item = self._queue.get(timeout=timeout)
            except queue.Empty:
                if batch:
                    self._send_batch(batch)
                    batch = []
                    last_flush = time.time()
                continue

            if item is _SEQ_STOP:
                if batch:
                    self._send_batch(batch)
                # Дочитываем остаток очереди без ожидания новых событий.
                while True:
                    try:
                        leftover = self._queue.get_nowait()
                    except queue.Empty:
                        break
                    if leftover is _SEQ_STOP:
                        continue
                    batch.append(str(leftover))
                    if len(batch) >= self.batch_size:
                        self._send_batch(batch)
                        batch = []
                if batch:
                    self._send_batch(batch)
                return

            batch.append(str(item))
            if len(batch) >= self.batch_size:
                self._send_batch(batch)
                batch = []
                last_flush = time.time()

    def _send_batch(self, batch: list[str]) -> None:
        """Отправляет пачку событий в Seq. Вызывается только из воркера."""
        if not batch:
            return

        if time.time() < self._circuit_open_until:
            self._dropped_count += len(batch)
            return

        events: list[dict[str, Any]] = []
        for event_str in batch:
            try:
                event = json.loads(event_str)
                if "Timestamp" in event and "MessageTemplate" in event:
                    events.append(event)
                else:
                    self._logger.warning(
                        "Invalid Seq event skipped: %s", event_str[:100]
                    )
            except json.JSONDecodeError:
                self._logger.error(
                    "JSON parse error for Seq event: %s",
                    event_str[:100],
                    exc_info=True,
                )

        if not events:
            return

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Seq-ApiKey"] = self.api_key

        try:
            response = requests.post(
                f"{self.server_url}/api/events/raw",
                json={"Events": events},
                headers=headers,
                timeout=SEQ_TIMEOUT,
            )
            response.raise_for_status()
            self._fail_count = 0
            self._circuit_open_until = 0.0
        except RequestException as e:
            self._fail_count += 1
            # Без exc_info: иначе urllib3-stack смешивается с queue.Empty воркера.
            self._logger.error("Network error sending to Seq: %s", e)
            self._open_circuit_if_needed()
        except (ValueError, TypeError) as e:
            self._fail_count += 1
            self._logger.error("Data error sending to Seq: %s", e)
            self._open_circuit_if_needed()
        except Exception as e:
            self._fail_count += 1
            self._logger.error(
                "Unexpected error sending to Seq: %s",
                e,
                exc_info=True,
            )
            self._open_circuit_if_needed()

    def _open_circuit_if_needed(self) -> None:
        """Открывает circuit breaker после серии ошибок отправки."""
        if self._fail_count < SEQ_MAX_FAILURES:
            return
        self._circuit_open_until = time.time() + SEQ_CIRCUIT_COOLDOWN_SECONDS
        self._logger.warning(
            "Seq circuit open for %.0fs after %d failures",
            SEQ_CIRCUIT_COOLDOWN_SECONDS,
            self._fail_count,
        )
        self._fail_count = 0


# ===== Форматтер для Seq (Raw Events JSON) =====
class SeqClefFormatter(logging.Formatter):
    """
    Форматтер событий Seq для endpoint ``/api/events/raw``.

    Документация: https://docs.datalust.co/docs/posting-raw-events
    """

    def __init__(self) -> None:
        super().__init__(datefmt="%Y-%m-%dT%H:%M:%S.%f")

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        """
        Возвращает время события в формате ISO 8601 с миллисекундами и
        суффиксом Z (UTC).
        """
        dt = datetime.fromtimestamp(record.created, tz=UTC)
        return dt.strftime(datefmt or "%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def format(self, record: logging.LogRecord) -> str:
        """Форматирует запись в JSON-событие с защитой от падений."""
        try:
            return self._format_impl(record)
        except Exception as e:  # noqa: BLE001
            # Fallback: если всё упало, возвращаем безопасный минимальный JSON
            return json.dumps(
                {
                    "Timestamp": self.formatTime(record),
                    "MessageTemplate": str(record.getMessage()),
                    "Level": "ERROR",
                    "Properties": {
                        "RenderingError": str(e),
                        "OriginalMessage": str(record.msg),
                    },
                },
                ensure_ascii=False,
            )

    def _format_impl(self, record: logging.LogRecord) -> str:
        """Реальная логика форматирования."""

        # Обязательные поля CLEF
        event: dict[str, Any] = {
            "Timestamp": self.formatTime(record),  # @t
            "MessageTemplate": str(record.getMessage()),  # @mt
            "Level": record.levelname,
        }

        # Исключение (если есть)
        if record.exc_info:
            event["Exception"] = self.formatException(record.exc_info)  # @x

        # Формируем контекстные свойства
        properties: dict[str, Any] = {
            "Logger": record.name,
            "ProcessId": record.process,
            "ThreadId": record.thread,
            "FileName": record.filename,
            "LineNumber": record.lineno,
            "Function": record.funcName,
        }

        #  Кастомные поля из фильтра (module_name, class_name, method_name)
        for attr, dest in FILTER_FIELDS:
            val = getattr(record, attr, None)
            if val:
                properties[dest] = val

        # Все поля из extra (исключая системные)
        for key, value in record.__dict__.items():
            if key not in properties and key not in SYSTEM_FIELDS:
                # Сериализуем сложные объекты в строки
                if isinstance(value, str | int | float | bool | type(None)):
                    if isinstance(value, str) and not is_safe_log_key(key):
                        properties[key] = redact_key_value(key, value)
                    else:
                        properties[key] = value
                else:
                    redacted = redact_log_value(key, value)
                    try:
                        properties[key] = json.dumps(
                            redacted, default=str, ensure_ascii=False
                        )
                    except Exception:  # noqa: BLE001
                        properties[key] = str(redacted)

        # Добавляем свойства к событиям
        if properties:
            event["Properties"] = properties

        return json.dumps(event, ensure_ascii=False)


# ===== Фильтр контекста, caller info и маскирования =====
class CallerInfoFilter(logging.Filter):
    """
    Добавляет module_name/method_name из LogRecord, поля корреляции
    из ContextVar и маскирует секреты в extra.

    Не вызывает inspect.stack(). class_name берётся из extra или контекста.
    Фильтр вешается на root-логгер один раз.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "module_name", None):
            record.module_name = record.pathname or ""
        if not getattr(record, "method_name", None):
            record.method_name = record.funcName or ""
        if not getattr(record, "class_name", None):
            record.class_name = get_class_name() or ""

        request_id = getattr(record, "request_id", None) or get_request_id()
        if request_id:
            record.request_id = request_id
            if not getattr(record, "correlation_id", None):
                record.correlation_id = request_id

        run_id = getattr(record, "run_id", None) or get_run_id()
        if run_id:
            record.run_id = run_id

        job_name = getattr(record, "job_name", None) or get_job_name()
        if job_name:
            record.job_name = job_name

        for key, value in list(record.__dict__.items()):
            if key in SYSTEM_FIELDS:
                continue
            if is_safe_log_key(key) and isinstance(value, str):
                continue
            if isinstance(value, str):
                setattr(record, key, redact_key_value(key, value))
            elif isinstance(value, dict | list | tuple):
                setattr(record, key, redact_log_value(key, value))
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        return True


# ===== Форматтер для консоли и файла =====
json_formatter = JsonFormatter(
    fmt=(
        "%(asctime)s %(levelname)s %(name)s %(module_name)s %(class_name)s "
        "%(method_name)s %(message)s"
    ),
    datefmt="%Y-%m-%dT%H:%M:%S",
    json_encoder=None,
)


# ===== Конфигурация логирования (dictConfig) =====
def _build_logging_config(log_level: str | LogLevel) -> dict[str, Any]:
    """Собирает dictConfig с уровнем из настроек сервиса."""
    level = str(log_level)
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "caller_info": {"()": CallerInfoFilter},
        },
        "formatters": {
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "fmt": (
                    "%(asctime)s %(levelname)s %(name)s %(module_name)s "
                    "%(class_name)s %(method_name)s %(message)s"
                ),
                "datefmt": "%Y-%m-%dT%H:%M:%S",
            },
            "default": {
                "()": "uvicorn.logging.DefaultFormatter",
                "fmt": "%(levelprefix)s %(message)s",
                "use_colors": None,
            },
            "access": {
                "()": "uvicorn.logging.AccessFormatter",
                "fmt": (
                    "%(levelprefix)s %(client_addr)s - "
                    "'%(request_line)s' %(status_code)s"
                ),
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            },
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            },
            "access": {
                "class": "logging.StreamHandler",
                "formatter": "access",
                "stream": "ext://sys.stdout",
            },
        },
        "loggers": {
            "": {
                "handlers": ["console"],
                "level": level,
                "propagate": True,
                "filters": ["caller_info"],
            },
            "uvicorn.error": {
                "level": level,
                "handlers": ["default"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": level,
                "handlers": ["access"],
                "propagate": False,
            },
        },
    }


# ===== Функции для создания дополнительных хендлеров =====
def _create_file_handler(app_settings: AppSettings) -> RotatingFileHandler | None:
    """Создаёт файловый хендлер с ротацией. Возвращает None при ошибке."""
    try:
        log_dir = Path(app_settings.base_dir) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        handler = RotatingFileHandler(
            log_dir / "log.json",
            maxBytes=getattr(app_settings, "logging_file_max_bytes", FILE_MAX_BYTES),
            backupCount=getattr(
                app_settings, "logging_backup_count", FILE_BACKUP_COUNT
            ),
            encoding="utf-8",
        )
        handler.setFormatter(json_formatter)
        handler.setLevel(app_settings.log_level)
    except (OSError, PermissionError, ValueError) as e:
        logging.getLogger(__name__).error(
            "Failed to create file handler: %s", e, exc_info=True
        )
        return None
    except Exception as e:
        logging.getLogger(__name__).error(
            "Unexpected error creating file handler: %s",
            e,
            exc_info=True,
        )
        return None
    else:
        return handler


def _create_seq_handler(seq_settings: SeqSettings) -> logging.Handler | None:
    """
    Создаёт хендлер для отправки логов в Seq. Возвращает None при ошибке.
    """
    if not seq_settings.url or not seq_settings.is_enabled:
        return None

    try:
        handler = SeqJsonHandler(
            server_url=seq_settings.url,
            api_key=seq_settings.api_key,
            batch_size=SEQ_BATCH_SIZE,
        )
        handler.setFormatter(SeqClefFormatter())
        handler.setLevel(getattr(logging, seq_settings.level.upper(), logging.INFO))
    except (ValueError, TypeError, OSError) as e:
        logging.getLogger(__name__).error(
            "Seq handler configuration error: %s", e, exc_info=True
        )
        return None
    except Exception as e:
        logging.getLogger(__name__).error(
            "Unexpected error creating Seq handler: %s",
            e,
            exc_info=True,
        )
        return None
    else:
        return handler


# ===== Патчинг хендлеров (инициализация) =====
def patch_logging_handlers(
    app_settings: AppSettings,
    seq_settings: SeqSettings,
) -> None:
    """
    Добавляет файловый и Seq хендлеры к корневому логгеру (без дублирования).
    """
    root = logging.getLogger()

    # Флаги успешного создания для логирования в конце
    file_enabled = False
    seq_enabled = False
    seq_url = ""

    # 1. Файловый хендлер
    if getattr(app_settings, "log_to_file", False):
        already_has_file = any(
            isinstance(h, RotatingFileHandler) for h in root.handlers
        )
        if not already_has_file:
            file_handler = _create_file_handler(app_settings)
            if file_handler:
                root.addHandler(file_handler)
                file_enabled = True

    # 2. Seq хендлер
    if seq_settings.url and seq_settings.is_enabled:
        already_has_seq = any(isinstance(h, SeqJsonHandler) for h in root.handlers)
        if not already_has_seq:
            seq_handler = _create_seq_handler(seq_settings)
            if seq_handler:
                root.addHandler(seq_handler)
                seq_enabled = True
                seq_url = seq_settings.url

    # 3. Логируем статус только ПОСЛЕ настройки,
    # чтобы логи попали в новый хендлер
    if file_enabled:
        logging.getLogger(__name__).info("File logging enabled")

    if seq_enabled:
        logging.getLogger(__name__).info("Seq logging enabled: %s", seq_url)
    else:
        logging.getLogger(__name__).info(
            "Seq logging disabled (set SEQ_ENABLED=true and SEQ_URL)"
        )


# ===== Настройка уровня логов внешних библиотек =====
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)


# ===== Инициализация модуля =====
_init_done = False
_app_settings: AppSettings | None = None
_seq_settings: SeqSettings | None = None


def _shutdown_logging() -> None:
    """Корректно закрывает хендлеры, включая фоновый Seq-воркер."""
    root = logging.getLogger()
    for handler in list(root.handlers):
        try:
            handler.flush()
        except Exception:  # noqa: BLE001
            pass
        try:
            handler.close()
        except Exception:  # noqa: BLE001
            pass
    logging.shutdown()


def configure_logging(*, env_file: str | Path | None = None) -> None:
    """
    Инициализирует логирование из APP_* / SEQ_* (process env и файл сервиса).

    Идемпотентно: повторные вызовы игнорируются.
    Вызывать из ``core.logger`` сервиса до первого get_logger.

    Args:
        env_file: ``.env.price_flow`` / ``.env.converter`` / ``.env.upd_sites``.
            Если None — берётся ENV_FILE или только process env (Docker).
    """
    global _init_done, _app_settings, _seq_settings
    if _init_done:
        return

    resolved = env_file or os.getenv("ENV_FILE")
    _app_settings = load_prefixed_settings(AppSettings, resolved)
    _seq_settings = load_prefixed_settings(SeqSettings, resolved)

    logging.config.dictConfig(_build_logging_config(_app_settings.log_level))
    patch_logging_handlers(_app_settings, _seq_settings)

    sync_logger = logging.getLogger("sync")
    sync_logger.propagate = True
    sync_logger.setLevel(getattr(_app_settings, "log_level", LogLevel.INFO))

    atexit.register(_shutdown_logging)
    _init_done = True


def get_app_settings() -> AppSettings:
    """Возвращает настройки приложения, использованные логгером."""
    configure_logging()
    if _app_settings is None:
        raise RuntimeError("Logging AppSettings were not initialized")
    return _app_settings


def get_logger(name: str) -> logging.Logger:
    """Возвращает настроенный логгер указанного модуля."""
    configure_logging()
    return logging.getLogger(name)
