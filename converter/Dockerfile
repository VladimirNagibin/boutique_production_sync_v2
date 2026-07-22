FROM python:3.11.10-slim-bullseye AS base

COPY common/ /opt/app/common/

WORKDIR /opt/app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY  ./converter/pyproject.toml /opt/app/


RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir poetry==2.0.1 \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi \
    && rm -rf $(poetry config cache-dir)/{cache,artifacts}

COPY ./converter/src /opt/app
RUN mkdir -p /opt/app/data/upload/in /opt/app/data/upload/out

ENV PYTHONPATH="/opt/app:/opt/app/common"

FROM base AS production

ENTRYPOINT ["python3", "/opt/app/main.py"]
