FROM ghcr.io/astral-sh/uv:python3.12-bookworm

USER root

WORKDIR /app

SHELL ["/bin/bash", "-c"]

ENV UV_LINK_MODE=copy

# Copy dependency files first for better caching
COPY uv.lock pyproject.toml README.md ./
COPY app/ ./app/

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-cache --all-extras

# Copy the rest of the application
COPY . .
