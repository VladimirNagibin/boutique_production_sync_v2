from __future__ import annotations

import json
import time
import uuid

from typing import TYPE_CHECKING, cast

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from core.logger import get_logger


logger = get_logger(__name__)


if TYPE_CHECKING:
    from fastapi import Request
    from starlette.middleware.base import RequestResponseEndpoint


# ===== Middleware для измерения времени выполнения запроса =====
SLOW_REQUEST_THRESHOLD_MS = 1000.0


class ExecutionTimeMiddleware(BaseHTTPMiddleware):
    """
    Middleware для измерения времени выполнения запроса и добавления метрик
    в ответ.

    - Добавляет в заголовки ответа:
        - `X-Request-ID`: идентификатор запроса (берётся из заголовка запроса
          или генерируется новый UUID).
        - `X-Execution-Time-Ms`: время выполнения запроса в миллисекундах.
    - Если ответ имеет Content-Type `application/json`, middleware также
      модифицирует тело ответа, добавляя в JSON‑объект поля:
        - `execution_time` (время выполнения в миллисекундах)
        - `request_id` (тот же идентификатор, что и в заголовке).
    - При невозможности модифицировать JSON (ошибка парсинга, отсутствие
      `body_iterator` и т.п.) ответ возвращается без изменений, но заголовки
      всё равно добавляются.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Обрабатывает входящий запрос и исходящий ответ."""
        start_time = time.perf_counter()
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        request.state.request_started_at = start_time

        # Передаем управление следующему middleware или эндпоинту
        response = await call_next(request)

        execution_time = round((time.perf_counter() - start_time) * 1000.0, 4)
        request.state.execution_time_ms = execution_time
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Execution-Time-Ms"] = str(execution_time)

        if execution_time >= SLOW_REQUEST_THRESHOLD_MS:
            logger.warning(
                "Slow request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "execution_time_ms": execution_time,
                    "threshold_ms": SLOW_REQUEST_THRESHOLD_MS,
                },
            )

        # Модифицируем только JSON-ответы
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("application/json"):
            body_iterator = getattr(response, "body_iterator", None)
            if body_iterator is None:
                logger.warning(
                    "Response missing body iterator",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                    },
                )
                return response

            body = b""
            try:
                async for chunk in body_iterator:
                    # chunk должен быть bytes, используем cast для указания
                    # типа
                    body += cast("bytes", chunk)
            except Exception as e:
                logger.error(
                    "Failed to read response body",
                    extra={
                        "request_id": request_id,
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )
                return response

            try:
                # Пытаемся распарсить JSON для добавления метрики времени
                data = json.loads(body.decode())

                if isinstance(data, dict):
                    data["execution_time"] = execution_time
                    data["request_id"] = request_id
                    # Формируем новый ответ с обновленным телом.
                    # Удаляем Content-Length, так как длина изменилась.
                    headers = dict(response.headers)
                    headers.pop("content-length", None)

                    return JSONResponse(
                        content=data,
                        status_code=response.status_code,
                        headers=headers,
                        media_type=response.media_type,
                    )
            except json.JSONDecodeError as e:
                logger.warning(
                    "Failed to parse JSON response",
                    extra={
                        "request_id": request_id,
                        "error_type": type(e).__name__,
                    },
                )
            except UnicodeDecodeError as e:
                logger.warning(
                    "Failed to decode response body",
                    extra={
                        "request_id": request_id,
                        "error_type": type(e).__name__,
                    },
                )
            except (ValueError, TypeError) as e:
                # Неожиданный формат данных (например, data не dict)
                logger.error(
                    "Unexpected JSON response data format",
                    extra={
                        "request_id": request_id,
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )
            except Exception as e:
                # Логируем любые неожиданные ошибки при модификации
                logger.error(
                    "Unexpected response instrumentation error",
                    extra={
                        "request_id": request_id,
                        "error_type": type(e).__name__,
                    },
                    exc_info=True,
                )

            # Если не смогли модифицировать JSON, возвращаем исходное тело
            # как есть
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        return response
