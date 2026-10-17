#!/usr/bin/env bash
# Rebuild the application images and apply code or .env changes to the stack.
set -euo pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "[update] ERROR: docker CLI not found." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "[update] ERROR: .env is missing. Copy .env.example and configure it first." >&2
  exit 1
fi

DOCKER_ARCH="$(docker info --format '{{.Architecture}}')"
case "$DOCKER_ARCH" in
  aarch64|arm64)
    export DOCKER_DEFAULT_PLATFORM=linux/arm64
    ;;
  x86_64|amd64)
    export DOCKER_DEFAULT_PLATFORM=linux/amd64
    ;;
  *)
    echo "[update] ERROR: unsupported Docker daemon architecture: $DOCKER_ARCH" >&2
    exit 1
    ;;
esac

echo "[update] validating Docker Compose configuration for $DOCKER_DEFAULT_PLATFORM..."
docker compose config --quiet

UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://mirrors.aliyun.com/pypi/simple/}"
echo "[update] rebuilding the shared api/bot application image..."
docker compose build --build-arg "UV_DEFAULT_INDEX=$UV_DEFAULT_INDEX" api

IMAGE_PLATFORM="$(docker image inspect realtimestock-bot:latest --format '{{.Os}}/{{.Architecture}}')"
if [[ "$IMAGE_PLATFORM" != "$DOCKER_DEFAULT_PLATFORM" ]]; then
  echo "[update] ERROR: expected $DOCKER_DEFAULT_PLATFORM but built $IMAGE_PLATFORM; containers were not restarted." >&2
  exit 1
fi
echo "[update] verified application image platform: $IMAGE_PLATFORM"

echo "[update] recreating affected containers..."
docker compose up -d --no-build

echo "[update] stack status:"
docker compose ps
