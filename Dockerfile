# syntax=docker/dockerfile:1
ARG PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright/python:v1.49.0-noble
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.5
FROM ${UV_IMAGE} AS uv
FROM ${PLAYWRIGHT_IMAGE} AS base

WORKDIR /app
COPY --from=uv /uv /uvx /usr/local/bin/

ARG TARGETOS
ARG TARGETARCH
RUN test "${TARGETOS}" = "linux" \
    && test "${TARGETARCH}" = "$(dpkg --print-architecture)" \
    && echo "Verified build target and userland: ${TARGETOS}/${TARGETARCH}"

# System dependencies and the Python environment change less often than the app,
# so keep their layers ahead of the application source for code-only rebuilds.
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements-docker.txt .
ARG UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --default-index "${UV_DEFAULT_INDEX}" -r requirements-docker.txt

ARG WHISPER_MODEL=small
ENV WHISPER_MODEL=${WHISPER_MODEL}
ENV HF_HOME=/app/.cache/huggingface
ENV HF_ENDPOINT=https://hf-mirror.com
ENV HF_HUB_DISABLE_XET=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN useradd --create-home --shell /bin/bash bot \
    && mkdir -p /app/app/data/series /app/.cache/huggingface \
    && chown -R bot:bot /app
USER bot

# Bake the Whisper model into the image as the runtime user. This layer remains
# valid when only application source changes.
RUN python -c "import os; from faster_whisper import WhisperModel; WhisperModel(os.environ['WHISPER_MODEL'], device='cpu', compute_type='int8')"

COPY --chown=bot:bot config.py .
COPY --chown=bot:bot scripts ./scripts
COPY --chown=bot:bot alembic.ini ./
COPY --chown=bot:bot --chmod=755 entrypoint.sh .
COPY --chown=bot:bot app app/

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "scripts.run_telegram_bot"]
