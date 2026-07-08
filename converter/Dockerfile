FROM python:3.11.10-slim-bullseye

WORKDIR /opt/app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY  ./pyproject.toml /opt/app/


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

COPY ./src /opt/app
RUN mkdir -p /opt/app/data/upload/in /opt/app/data/upload/out


ENTRYPOINT ["python3", "/opt/app/main.py"]
