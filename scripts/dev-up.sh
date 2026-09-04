#!/usr/bin/env bash
# Dev environment quick-start for Kora Bourse (mini Mac).
# Starts the API (background) and launches the already-installed app on the
# Android emulator + iOS simulator. Run: bash scripts/dev-up.sh
set -u
cd "$(dirname "$0")/.."

API_PORT=8002
PYTHON=.venv/bin/python
[[ -x "$PYTHON" ]] || PYTHON=python3

export DATABASE_URL="" \
       JWT_SECRET=dev-mobile-secret-ChangeMe0123456789abcdef \
       AUTH_PROVIDER=mock \
       API_PORT=$API_PORT \
       API_BIND=0.0.0.0
# Tavily key comes from .env (needed for the news fallback chain).
TAVILY=$(grep -s '^TAVILY_API_KEY=' .env | cut -d= -f2-)
[[ -n "$TAVILY" ]] && export TAVILY_API_KEY="$TAVILY"

# Cloudflare tunnel: expose the API on https://kbourse.neobytech.net
if ! pgrep -f "cloudflared tunnel.*kora-api" > /dev/null; then
  echo "Starting Cloudflare tunnel (kbourse.neobytech.net)"
  nohup cloudflared tunnel --config "$HOME/.cloudflared/kora-api.yml" run kora-api >> /tmp/kora-tunnel.log 2>&1 &
else
  echo "Tunnel already running"
fi

if curl -s --max-time 2 "http://127.0.0.1:$API_PORT/health" | grep -q ok; then
  echo "API already running on :$API_PORT"
else
  echo "Starting API on :$API_PORT (log: /tmp/kora-api.log)"
  nohup env DATABASE_URL="" JWT_SECRET="$JWT_SECRET" AUTH_PROVIDER=mock \
        API_PORT=$API_PORT ${TAVILY_API_KEY:+TAVILY_API_KEY=$TAVILY_API_KEY} \
        "$PYTHON" -m scripts.run_api > /tmp/kora-api.log 2>&1 &
  for _ in $(seq 1 20); do
    curl -s --max-time 1 "http://127.0.0.1:$API_PORT/health" | grep -q ok && break
    sleep 1
  done
  curl -s --max-time 2 "http://127.0.0.1:$API_PORT/health" | grep -q ok \
    && echo "API: OK" || { echo "API failed to start; see /tmp/kora-api.log"; exit 1; }
fi

# Android emulator (app must have been installed once via flutter run).
if adb devices | grep -q emulator; then
  adb shell monkey -p com.neobytech.korabourse -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1 \
    && echo "Android: app launched"
else
  echo "Android: no emulator connected (start it or run: flutter run -d emulator-5554)"
fi

# iOS simulator (app must have been installed once via flutter run).
SIM=$(xcrun simctl list devices booted | grep -oE '[0-9A-F-]{36}' | head -1)
if [[ -n "$SIM" ]]; then
  xcrun simctl launch "$SIM" com.neobytech.korabourse >/dev/null 2>&1 \
    && echo "iOS: app launched" \
    || echo "iOS: app not installed on booted simulator (run once: flutter run -d <sim-id>)"
else
  echo "iOS: no simulator booted"
fi

echo "Done. Login: ⚡ 'Explorer sans compte (mode démo)' — the demo account is shared by both devices."
