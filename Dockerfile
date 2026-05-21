# Pulse backend — FastAPI + agent on Python 3.12
FROM python:3.12-slim

# uv for fast, reproducible installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PULSE_HOST=0.0.0.0 \
    PULSE_PORT=8787 \
    PULSE_DATA_DIR=/data

WORKDIR /app

# install deps first (cached layer) — needs the package source for the editable install
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

COPY config.yaml ./

# data dir (db, settings.json) — mount a volume here to persist
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8787
CMD ["uv", "run", "--no-dev", "pulse"]
