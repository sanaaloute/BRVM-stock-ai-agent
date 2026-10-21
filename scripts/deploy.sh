#!/usr/bin/env bash
# Build and start the complete Docker Compose stack for a first deployment.
set -euo pipefail

export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "[deploy] ERROR: docker CLI not found." >&2
  exit 1
fi

if [[ ! -f .env ]]; then
  echo "[deploy] ERROR: .env is missing. Copy .env.example to .env and configure it first." >&2
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
    echo "[deploy] ERROR: unsupported Docker daemon architecture: $DOCKER_ARCH" >&2
    exit 1
    ;;
esac

echo "[deploy] validating Docker Compose configuration for $DOCKER_DEFAULT_PLATFORM..."
docker compose config --quiet

UV_DEFAULT_INDEX="${UV_DEFAULT_INDEX:-https://mirrors.aliyun.com/pypi/simple/}"
echo "[deploy] building the application image..."
docker compose build --build-arg "UV_DEFAULT_INDEX=$UV_DEFAULT_INDEX" api

IMAGE_PLATFORM="$(docker image inspect realtimestock-bot:latest --format '{{.Os}}/{{.Architecture}}')"
if [[ "$IMAGE_PLATFORM" != "$DOCKER_DEFAULT_PLATFORM" ]]; then
  echo "[deploy] ERROR: expected $DOCKER_DEFAULT_PLATFORM but built $IMAGE_PLATFORM; stack was not started." >&2
  exit 1
fi
echo "[deploy] verified application image platform: $IMAGE_PLATFORM"

echo "[deploy] starting the stack..."
docker compose up -d

echo "[deploy] stack status:"
docker compose ps
