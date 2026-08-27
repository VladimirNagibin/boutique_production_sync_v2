# Общий этап для копирования файлов зависимостей
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS base

# Структура как в репозитории: ../common относительно updating_sites/
WORKDIR /workspace
COPY common/ /workspace/common/
COPY ./updating_sites/pyproject.toml ./updating_sites/uv.lock /workspace/updating_sites/

WORKDIR /workspace/updating_sites

# ---- Продакшен-зависимости (без dev) ----
FROM base AS prod-deps
RUN uv sync --frozen --no-cache --no-dev

# ---- Dev-зависимости (все, включая инструменты) ----
FROM base AS dev-deps
RUN uv sync --frozen --no-cache --group dev

# ---- Финальный образ для продакшена ----
FROM python:3.13-slim-bookworm AS production

WORKDIR /app

# mysqldump нужен portals.py; PyMySQL — pure Python, libmysqlclient не требуется
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-mysql-client \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Создаём непривилегированного пользователя
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Копируем только продакшен-окружение
COPY --from=prod-deps --chown=appuser:appuser /workspace/updating_sites/.venv /app/.venv

# Копируем исходный код
COPY --chown=appuser:appuser updating_sites/src/ ./src/
COPY --chown=appuser:appuser common/ ./src/common/

# Переменные окружения
ENV PYTHONPATH="/app/src:/app/src/common" \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Данные и логи
RUN mkdir -p \
        /app/src/data/storage \
        /app/src/data/upload \
        /app/src/data/prices \
        /app/src/data/butic \
        /app/src/data/ismy \
        /app/src/data/ornam \
        /app/src/logs \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["python", "/app/src/main.py"]

# ---- Образ для разработки (с dev-зависимостями) ----
FROM python:3.13-slim-bookworm AS development

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    vim \
    default-mysql-client \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY --from=dev-deps /workspace/updating_sites/.venv /app/.venv

COPY updating_sites/src/ ./src/
COPY common/ ./src/common/

ENV PYTHONPATH="/app/src:/app/src/common" \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

RUN mkdir -p \
        /app/src/data/storage \
        /app/src/data/upload \
        /app/src/data/prices \
        /app/src/data/butic \
        /app/src/data/ismy \
        /app/src/data/ornam \
        /app/src/logs

EXPOSE 8000

CMD ["python", "/app/src/main.py"]
