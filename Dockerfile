FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libarchive-tools \
        tini \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Install dependencies first for better layer caching
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# Copy source and install project
COPY src ./src
RUN uv sync --frozen --no-dev

RUN mkdir -p /data
VOLUME ["/data"]

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/data \
    TELEGRAM_FILES_DIR=/var/lib/telegram-bot-api \
    TELEGRAM_API_BASE=http://telegram-bot-api:8081

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -m immich_chat_importer.healthcheck || exit 1

ENTRYPOINT ["tini", "--"]
CMD ["python", "-m", "immich_chat_importer"]

