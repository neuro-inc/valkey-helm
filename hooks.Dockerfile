FROM python:3.13-slim

LABEL org.opencontainers.image.source="https://github.com/neuro-inc/app-valkey"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=0 \
    APOLO_CONFIG=/app/.apolo

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY README.md poetry.lock pyproject.toml /app/
COPY .apolo .apolo
RUN pip --no-cache-dir install poetry && poetry install --only-root --no-cache

ENTRYPOINT ["app-types"]
