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
# for speech recognition (pydub shells out to ffmpeg/ffprobe).
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Entrypoint bootstraps SGI (broker) data into the shared volume on startup.
ENTRYPOINT ["/app/entrypoint.sh"]

# Default: run Telegram bot. Override to run CLI agent: python run_agent.py "query"
CMD ["python", "run_telegram_bot.py"]
