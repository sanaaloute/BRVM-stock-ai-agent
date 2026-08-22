#!/usr/bin/env bash
# Backup the BRVM stack (Postgres + named volumes) on the production host.
#
# Creates ./backups/YYYYMMDD-HHMMSS/ containing:
#   postgres.sql          pg_dump of the brvm database
#   evolution.sql         pg_dump of the evolution database (skipped if missing)
#   bot_data.tar.gz       archive of the bot_data named volume
#   evolution_data.tar.gz archive of the evolution_data named volume
# then deletes backup directories older than 14 days.
#
# Override the destination root with BACKUP_DIR. Schedule via cron — see
# README.md, "Production hardening". The compose stack must be up (pg_dump goes
# through `docker compose exec db`). Compatible with macOS bash 3.2.
set -euo pipefail

# cron on macOS has a minimal PATH; make sure the docker CLI is reachable.
export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"

# Repo root = parent of this script's directory, so the script also works from
# cron regardless of the caller's working directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

TS="$(date +%Y%m%d-%H%M%S)"
BACKUP_ROOT="${BACKUP_DIR:-$PROJECT_DIR/backups}"
DEST="$BACKUP_ROOT/$TS"

# Guard against a catastrophic `rm -rf` on a misconfigured BACKUP_DIR.
case "$BACKUP_ROOT" in
  ""|/|/Users|/Users/*|/home|/home/*)
    echo "[backup] ERROR: unsafe BACKUP_DIR: '$BACKUP_ROOT'" >&2
    exit 1
    ;;
esac

mkdir -p "$DEST"
echo "[backup] destination: $DEST"

# Compose project name: COMPOSE_PROJECT_NAME if set, else the directory
# basename, normalized the way compose does — named volumes are prefixed with it.
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-$(basename "$PROJECT_DIR")}"
PROJECT_NAME="$(printf '%s' "$PROJECT_NAME" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"

# --- Databases --------------------------------------------------------------
echo "[backup] dumping Postgres database 'brvm'..."
docker compose exec -T db pg_dump -U brvm -d brvm > "$DEST/postgres.sql"

# The evolution database only exists on installs that use the WhatsApp gateway;
# tolerate it missing.
if ! docker compose exec -T db pg_dump -U brvm -d evolution > "$DEST/evolution.sql"; then
  rm -f "$DEST/evolution.sql"
  echo "[backup] NOTE: database 'evolution' could not be dumped (does not exist?) — skipped."
fi

# --- Named volumes ----------------------------------------------------------
# Echoes the real volume name ("<project>_<key>"), or nothing if not found.
resolve_volume() {
  local vol
  vol="$(docker volume ls --format '{{.Name}}' | grep -E "^${PROJECT_NAME}_$1\$" | head -1 || true)"
  if [ -z "$vol" ]; then
    # Fallback: any project prefix, exact key suffix (e.g. COMPOSE_PROJECT_NAME
    # was set in .env and we couldn't see it).
    vol="$(docker volume ls --format '{{.Name}}' | grep -E "_$1\$" | head -1 || true)"
  fi
  printf '%s' "$vol"
}

backup_volume() {
  # $1 = compose volume key, $2 = archive file name
  local name
  name="$(resolve_volume "$1")"
  if [ -z "$name" ]; then
    echo "[backup] WARNING: no volume found for '$1' — skipped (stack deployed?)"
    return 0
  fi
  echo "[backup] archiving volume '$name'..."
  docker run --rm -v "$name:/data:ro" -v "$DEST:/backup" alpine \
    tar czf "/backup/$2" -C /data .
}

backup_volume bot_data bot_data.tar.gz
backup_volume evolution_data evolution_data.tar.gz

# --- Retention --------------------------------------------------------------
echo "[backup] pruning backups older than 14 days..."
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -name '????????-??????' -mtime +14 -exec rm -rf {} +

echo "[backup] done: $DEST"
