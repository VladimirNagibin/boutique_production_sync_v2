FROM python:3.11.10-slim-bullseye AS base

COPY common/ /opt/app/common/

WORKDIR /opt/app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

COPY  ./updating_sites/pyproject.toml /opt/app/

RUN apt-get update && apt-get install -y python3-dev default-libmysqlclient-dev build-essential pkg-config
RUN apt-get update && \
    apt-get install -y --no-install-recommends default-mysql-client && \
    rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir poetry==1.8.5 \
    && poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi \
    && rm -rf $(poetry config cache-dir)/{cache,artifacts}

COPY ./updating_sites/src /opt/app

ENV PYTHONPATH="/opt/app:/opt/app/common"

FROM base AS production

ENTRYPOINT ["python3", "/opt/app/main.py"]
