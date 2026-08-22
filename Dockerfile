# Use Playwright Python image (includes Chromium and system deps; match version to requirements)
ARG PLAYWRIGHT_IMAGE=mcr.microsoft.com/playwright/python:v1.49.0-noble
FROM ${PLAYWRIGHT_IMAGE} AS base

WORKDIR /app

# Install Python deps (playwright + Chromium already in base image; use requirements-docker to avoid greenlet conflict)
COPY requirements-docker.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements-docker.txt

# App and data
COPY config.py .
COPY run_agent.py run_api.py run_telegram_bot.py run_scrapers.py run_sgi_fetch.py ./
COPY run_migrations.py run_company_details_fetch.py ./
COPY alembic.ini ./
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh
COPY app app/

# Persisted at runtime via volume; ensure dir exists
RUN mkdir -p /app/app/data/series

# ffmpeg is required to convert Telegram/WhatsApp voice notes (OGG/OPUS) to WAV
# for the Google Speech fallback (pydub shells out to ffmpeg/ffprobe).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

# Pre-download the whisper model (voice-to-text) so the first voice note is fast
# and the container needs no Hugging Face access at runtime. Bakes ~250MB (small,
# int8) into the image. HF_HOME pins the Hugging Face cache under /app so the
# baked model lands in the tree owned by the runtime user (see below) and is
# found again at runtime. Override with: docker compose build --build-arg WHISPER_MODEL=base
ARG WHISPER_MODEL=small
ENV WHISPER_MODEL=${WHISPER_MODEL}
ENV HF_HOME=/app/.cache/huggingface
# huggingface.co is unreachable from some networks (the model bake fails with
# ConnectError). hf-mirror.com mirrors the Hub; HF_HUB_DISABLE_XET forces the
# plain-LFS path because the xet CAS backend (cas-server.xethub.hf.co) bypasses
# HF_ENDPOINT. On a network that reaches HF directly, override at runtime with
# HF_ENDPOINT=https://huggingface.co (container env beats image ENV).
ENV HF_ENDPOINT=https://hf-mirror.com
ENV HF_HUB_DISABLE_XET=1
RUN python -c "import os; from faster_whisper import WhisperModel; WhisperModel(os.environ['WHISPER_MODEL'], device='cpu', compute_type='int8')"

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Run as an unprivileged user. chown the whole /app tree so the code stays
# readable and the runtime-writable paths belong to it: /app/app/data (the
# bot_data volume mount point — named-volume copy-up inherits image ownership
# on first mount) and the HF_HOME whisper cache. Playwright browsers stay at
# /ms-playwright (base image default, already world read+execute).
RUN useradd --create-home --shell /bin/bash bot \
    && chown -R bot:bot /app
USER bot

# Entrypoint bootstraps SGI (broker) data into the shared volume on startup.
ENTRYPOINT ["/app/entrypoint.sh"]

# Default: run Telegram bot. Override to run CLI agent: python run_agent.py "query"
CMD ["python", "run_telegram_bot.py"]
