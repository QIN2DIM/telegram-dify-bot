FROM ghcr.io/astral-sh/uv:python3.12-bookworm

USER root

WORKDIR /app

SHELL ["/bin/bash", "-c"]

ENV UV_LINK_MODE=copy

# Install system dependencies including ffmpeg for yt-dlp
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Install Python dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=README.md,target=README.md \
    --mount=type=bind,source=app,target=app \
    uv sync --frozen --no-cache --all-extras

ADD . /app
