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

# Python dependencies change less often than the application source, so keep
# their layer ahead of the COPY lines below for fast code-only rebuilds.
COPY requirements-docker.txt .
ARG UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --default-index "${UV_DEFAULT_INDEX}" -r requirements-docker.txt

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN useradd --create-home --shell /bin/bash bot \
    && mkdir -p /app/app/data/series \
    && chown -R bot:bot /app
USER bot

COPY --chown=bot:bot config.py .
COPY --chown=bot:bot scripts ./scripts
COPY --chown=bot:bot alembic.ini ./
COPY --chown=bot:bot --chmod=755 entrypoint.sh .
COPY --chown=bot:bot app app/

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "-m", "scripts.run_api"]
