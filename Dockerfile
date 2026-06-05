# syntax=docker/dockerfile:1.7

FROM python:3.12-alpine@sha256:236173eb74001afe2f60862de935b74fcbd00adfca247b2c27051a70a6a39a2d AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.31-alpine@sha256:9fde210ef69f9f4b9b70b4155ca94e62accf7c53d857b6362ee5aa2236c98941 /usr/local/bin/uv /usr/local/bin/uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-alpine@sha256:236173eb74001afe2f60862de935b74fcbd00adfca247b2c27051a70a6a39a2d AS runtime

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN addgroup -S bot \
    && adduser -S -G bot -h /app -s /sbin/nologin bot

WORKDIR /app

COPY --from=builder --chown=bot:bot /app/.venv /app/.venv

USER bot

CMD ["optcg-card-bot"]
