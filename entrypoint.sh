#!/bin/sh
# Container entrypoint: best-effort SGI (broker) data bootstrap, then run the real command.
#
# Populates app/data/sgi_brvm.json when missing or older than SGI_REFRESH_DAYS
# (default 7), so no manual `python run_sgi_fetch.py` step is needed after deploy.
# Never blocks startup: if the fetch fails, SGI answers degrade gracefully.
set -e

DATA_DIR="${BOT_DATA_DIR:-/app/app/data}"
SGI_JSON="${SGI_JSON_PATH:-$DATA_DIR/sgi_brvm.json}"
DAYS="${SGI_REFRESH_DAYS:-7}"

mkdir -p "$DATA_DIR"

# Database schema migrations (Alembic): adopt/create tables before boot.
# Unlike the data fetches below, a schema failure MUST block startup.
echo "[entrypoint] Running database migrations..."
if command -v flock >/dev/null 2>&1; then
  flock "$DATA_DIR/.migrate.lock" python run_migrations.py || exit 1
else
  python run_migrations.py || exit 1
fi

# Data bootstraps run in the BACKGROUND: on first boot they fetch dozens of
# remote pages (SGI details ~2min, company fiches ~3-4min) and a foreground run
# would delay the server past its healthcheck window. Both scripts are
# idempotent and flock-guarded; answers degrade gracefully until data lands.
(
  stale=0
  if [ ! -s "$SGI_JSON" ]; then
    stale=1
  elif find "$SGI_JSON" -mtime +"$DAYS" 2>/dev/null | grep -q .; then
    stale=1
  fi

  if [ "$stale" = "1" ]; then
    echo "[entrypoint] SGI data missing or older than ${DAYS}d - fetching (best effort, background)..."
    # flock: api + bot share the data volume and may boot together on first deploy.
    if command -v flock >/dev/null 2>&1; then
      flock "$DATA_DIR/.sgi.lock" python run_sgi_fetch.py \
        || echo "[entrypoint] WARNING: SGI fetch failed (non-fatal); SGI answers may be limited."
    else
      python run_sgi_fetch.py \
        || echo "[entrypoint] WARNING: SGI fetch failed (non-fatal); SGI answers may be limited."
    fi
  fi

  # Company details bootstrap: refresh $DATA_DIR/company_details/ when empty or
  # holding files older than COMPANY_DETAILS_REFRESH_DAYS (default 7). The fetch
  # script skips fresh files itself. Best effort, never blocks startup.
  CD_DIR="$DATA_DIR/company_details"
  CD_DAYS="${COMPANY_DETAILS_REFRESH_DAYS:-7}"

  cd_stale=0
  if [ ! -d "$CD_DIR" ] || [ -z "$(ls -A "$CD_DIR" 2>/dev/null)" ]; then
    cd_stale=1
  elif find "$CD_DIR" -type f -mtime +"$CD_DAYS" 2>/dev/null | grep -q .; then
    cd_stale=1
  fi

  if [ "$cd_stale" = "1" ]; then
    echo "[entrypoint] company_details missing or older than ${CD_DAYS}d - fetching (best effort, background)..."
    if command -v flock >/dev/null 2>&1; then
      flock "$DATA_DIR/.company_details.lock" python run_company_details_fetch.py \
        || echo "[entrypoint] WARNING: company details fetch failed (non-fatal)."
    else
      python run_company_details_fetch.py \
        || echo "[entrypoint] WARNING: company details fetch failed (non-fatal)."
    fi
  fi
) &

exec "$@"
