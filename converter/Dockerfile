# Общий этап для копирования файлов зависимостей
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS base

# Структура как в репозитории: ../common относительно converter/
WORKDIR /workspace
COPY common/ /workspace/common/
COPY ./converter/pyproject.toml ./converter/uv.lock /workspace/converter/

WORKDIR /workspace/converter

# ---- Продакшен-зависимости (без dev) ----
FROM base AS prod-deps
RUN uv sync --frozen --no-cache --no-dev

# ---- Dev-зависимости (все, включая инструменты) ----
FROM base AS dev-deps
RUN uv sync --frozen --no-cache --group dev

# ---- Финальный образ для продакшена ----
FROM python:3.11-slim-bookworm AS production

WORKDIR /app

# Создаём непривилегированного пользователя
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Копируем только продакшен-окружение
COPY --from=prod-deps --chown=appuser:appuser /workspace/converter/.venv /app/.venv

# Копируем исходный код
COPY --chown=appuser:appuser converter/src/ ./src/
COPY --chown=appuser:appuser common/ ./src/common/

# Переменные окружения
ENV PYTHONPATH="/app/src:/app/src/common" \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Данные и логи
RUN mkdir -p /app/src/data/upload/in /app/src/data/upload/out /app/src/logs \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["python", "/app/src/main.py"]

# ---- Образ для разработки (с dev-зависимостями) ----
FROM python:3.11-slim-bookworm AS development

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    vim \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=dev-deps /workspace/converter/.venv /app/.venv

COPY converter/src/ ./src/
COPY common/ ./src/common/

ENV PYTHONPATH="/app/src:/app/src/common" \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN mkdir -p /app/src/data/upload/in /app/src/data/upload/out /app/src/logs

EXPOSE 8000

CMD ["python", "/app/src/main.py"]
