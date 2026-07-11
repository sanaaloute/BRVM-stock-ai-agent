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
# int8) into the image. Override with: docker compose build --build-arg WHISPER_MODEL=base
ARG WHISPER_MODEL=small
ENV WHISPER_MODEL=${WHISPER_MODEL}
RUN python -c "import os; from faster_whisper import WhisperModel; WhisperModel(os.environ['WHISPER_MODEL'], device='cpu', compute_type='int8')"

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Entrypoint bootstraps SGI (broker) data into the shared volume on startup.
ENTRYPOINT ["/app/entrypoint.sh"]

# Default: run Telegram bot. Override to run CLI agent: python run_agent.py "query"
CMD ["python", "run_telegram_bot.py"]
