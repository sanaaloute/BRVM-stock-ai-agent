# RealTimeStock

## Project objective

Scrape and query BRVM (Bourse Régionale des Valeurs Mobilières) / West African stock data. A LangGraph agent (NLU → supervisor → 10 workers) coordinates scrapers (Sika Finance, Rich Bourse, BRVM) and analytics workers to answer natural-language questions via CLI, Telegram, or WhatsApp. Supports portfolio tracking, price alerts, predictions/trends, SGI (broker) info, company fiches and deterministic investment advice.

## Mobile platform — Kora Bourse

The same engine powers **Kora Bourse**, a Flutter mobile app (Android + iOS) for regional investors: AI advisor chat ("Kora") with persistent conversation history, live market palmares with search/filters, rich stock detail (price chart, fundamentals, dividends, news, technical prediction), portfolio buy-lots with weighted-average positions, price alerts, daily digest and SGI broker profiles — all over an authenticated REST API (`/mobile/v1/*`: email-or-phone + password auth with JWT sessions, per-user quota, market snapshots served from the local DB with a scheduled post-close refresh). Source in [`mobile/`](mobile/README.md); app identity `com.neobytech.korabourse`. No Firebase dependency; push is pluggable via `PushService`.

## Project tree

```
RealTimeStock/
├── app/
│   ├── agents/           # LangGraph: NLU, supervisor, 10 workers, state
│   │   ├── graph.py             # master graph (cached compile, multi-worker routing)
│   │   ├── nlu_agent.py
│   │   ├── scraper_agent.py
│   │   ├── analytics_agent.py
│   │   ├── timeseries_agent.py
│   │   ├── charts_agent.py
│   │   ├── news_agent.py
│   │   ├── portfolio_agent.py
│   │   ├── prediction_agent.py
│   │   ├── sgi_agent.py
│   │   ├── company_details_agent.py
│   │   ├── advisor_agent.py     # investment advice (deterministic scoring engine)
│   │   ├── state.py
│   │   └── utils.py
│   ├── api/
│   │   ├── chat.py       # FastAPI: bot → API → agents (auth, quota, rate limit, sanitized errors)
│   │   └── whatsapp.py   # WhatsApp Business Cloud API webhook (same pipeline)
│   ├── models/           # LLM providers: ollama | tokenfree | openrouter
│   ├── bot/              # Telegram bot (client of the Chat API)
│   ├── channels/
│   │   └── whatsapp/     # WhatsApp via Evolution API (webhook, client, service)
│   ├── data/             # BRVM_Companies.xlsx, company_details/, series/ (runtime CSVs)
│   ├── db/               # SQLAlchemy engine/session + Alembic migrations (user data)
│   ├── scrapers/         # Rich Bourse, Sika Finance, BRVM.org (+ dividends, trends, SGI)
│   ├── services/
│   │   ├── chat_service.py  # Channel-agnostic entry to the AI pipeline
│   │   ├── scoring.py       # Deterministic 0-100 scoring engine (advisor)
│   │   ├── digest.py        # Scheduled digest composition + job body
│   │   ├── market_data.py   # Daily post-close market snapshots + scheduled refresh
│   │   ├── sgi_service.py   # SGI broker profiles (local DB list/detail)
│   │   ├── auth_service.py  # Mobile auth: email/phone + password (scrypt), OTP codes, JWT sessions, app-user identity
│   │   ├── otp_delivery.py  # OTP via SMTP / SMS provider / mock
│   │   ├── push.py          # FCM push (env-gated; disabled without credentials)
│   │   └── notify.py        # Channel-agnostic user notification dispatch
│   ├── tools/            # LangChain tools + pydantic schemas
│   └── utils/            # Services (metrics, news, plots, cache, user_db, ...)
├── mobile/               # Kora Bourse — Flutter app (Android + iOS), see mobile/README.md
├── config.py
├── main.py               # Single entry: API + Telegram bot
├── scripts/              # Entry-point scripts (run as `python -m scripts.<name>` from the repo root)
│   ├── run_agent.py            # CLI agent
│   ├── run_api.py              # API only
│   ├── run_telegram_bot.py     # Bot only (requires API)
│   ├── run_scrapers.py
│   ├── run_sgi_fetch.py        # Refresh SGI list into app/data/sgi_brvm.json
│   ├── run_migrations.py       # Apply Alembic migrations (native; the Docker entrypoint runs it too)
│   ├── run_company_details_fetch.py  # Refresh Sika Finance company fiches (fundamentals cache)
│   ├── dev-up.sh               # Dev quick-start (API + apps on emulators)
│   └── backup.sh               # Production backups
├── tests/                # Offline test suites (see below)
├── requirements.txt
├── requirements-docker.txt
├── .env.example
├── Dockerfile
└── docker-compose.yml
```

## Setup

1. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

   Voice notes: the Google Speech fallback (pydub) shells out to ffmpeg — install
   it natively (`brew install ffmpeg` on macOS, `sudo apt install ffmpeg` on
   Debian/Ubuntu). The Docker image already bundles it.

2. **Configure environment**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` and set at least:

   - `TAVILY_API_KEY` — [tavily.com](https://tavily.com)
   - LLM provider: `LLM_PROVIDER=ollama|tokenfree|openrouter` + the matching key/model (Ollama local, Ollama Cloud, TokenFree, or OpenRouter — see `.env.example`). Optional ordered fallback chain on upstream outages: `LLM_FALLBACK_PROVIDERS=tokenfree,openrouter` (each fallback is tried once, in order, when the primary provider's upstream is down).

   For the Telegram bot:

   - `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/BotFather)
   - `API_SECRET_KEY` — shared secret the bot sends to the Chat API (generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"`)

3. **Run**

   ```bash
   python -m scripts.run_scrapers              # scrape sites
   python -m scripts.run_agent "Price of NTLC?" # CLI agent
   ```

   **API + Telegram bot** (single process):

   ```bash
   python main.py
   ```

   **Or run separately** (two terminals):

   ```bash
   python -m scripts.run_api           # API only
   python -m scripts.run_telegram_bot  # Bot (requires API)
   ```

   Set `BRVM_API_URL` in `.env` if the API runs elsewhere (default `http://localhost:8000`).

   **WhatsApp channel** (WhatsApp Business Cloud API — served by the same Chat API, no extra process):

   1. Create a Meta app at [developers.facebook.com](https://developers.facebook.com), add the **WhatsApp** product, and note the *phone number ID* and a *permanent access token* (System User token).
   2. Set `WHATSAPP_VERIFY_TOKEN` (any secret you choose), `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` and `WHATSAPP_APP_SECRET` (Meta app → Settings → Basic → App Secret — verifies the `X-Hub-Signature-256` HMAC on inbound webhooks; the channel stays disabled without it) in `.env`.
   3. In the Meta app, configure the webhook: URL `https://<your-api-host>/whatsapp/webhook`, verify token = your `WHATSAPP_VERIFY_TOKEN`, subscribe to the `messages` field. The API must be reachable over **public HTTPS** (reverse proxy, or a tunnel like ngrok for dev).

   WhatsApp users share the Telegram pipeline: same agent, same free daily quota (metered as `wa:<phone>`), same per-user memory. Text in, text out; charts are sent as images. Voice/images on WhatsApp and portfolio/tracking/alerts on WhatsApp are not supported yet.

   **WhatsApp channel via Evolution API** (self-hosted alternative to the Meta Cloud API — same pipeline, no extra process):

   1. Set `EVOLUTION_API_KEY` (a secret you choose — generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`) and `EVOLUTION_INSTANCE` (e.g. `brvm-bot`) in `.env`. The `docker-compose.yml` stack already includes the `evolution` service (its API on port `8080`); for non-Docker runs also set `EVOLUTION_URL` (default inside compose: `http://evolution:8080`).
   2. Create the instance and pair your WhatsApp number (scan the QR with the phone app, like WhatsApp Web). Do NOT set a per-instance token, so webhook deliveries are signed with the global key:
      ```bash
      curl -X POST http://localhost:8080/instance/create \
        -H "apikey: $EVOLUTION_API_KEY" -H "Content-Type: application/json" \
        -d '{"instanceName": "brvm-bot", "integration": "WHATSAPP-BAILEYS", "qrcode": true}'
      # fetch the QR as base64 and open it in a browser:
      curl http://localhost:8080/instance/connect/brvm-bot -H "apikey: $EVOLUTION_API_KEY"
      ```
      (Or use the Manager UI at `http://localhost:8080/manager` — log in with your `EVOLUTION_API_KEY`.)
   3. Point the instance webhook at the api service (inside the compose network), with base64 enabled so voice notes arrive inline:
      ```bash
      curl -X POST http://localhost:8080/webhook/set/brvm-bot \
        -H "apikey: $EVOLUTION_API_KEY" -H "Content-Type: application/json" \
        -d '{"webhook": {"enabled": true, "url": "http://api:8000/whatsapp/evolution/webhook", "webhookByEvents": false, "webhookBase64": true, "events": ["MESSAGES_UPSERT"]}}'
      ```

   Text and voice notes (transcribed like Telegram) are supported; charts are sent as images. Users are metered as `wa:<phone>` with per-user conversation memory, identical to the Meta channel.

   **Production notes (Mac mini / Apple Silicon + EC2)** (Evolution channel):

   - **Apple Silicon runs natively**: every image in the stack — the pinned Playwright base (`mcr.microsoft.com/playwright/python:v1.49.0-noble`), `postgres:16-alpine`, `alpine` — has a `linux/arm64` manifest, so a Mac mini builds and runs the stack without emulation. One caveat: pull-test the Evolution image on the target host first (`docker pull evoapicloud/evolution-api:v2.3.7`) — its arm64 build is community-verified rather than officially supported.
   - **Auto-start on the Mac mini**: enable Docker Desktop → Settings → General → "Start Docker Desktop when you sign in", and turn on macOS automatic login for the service user, so the stack comes back after a reboot or power cut. (Alternative: run the Docker daemon natively under launchd instead of Docker Desktop.)
   - Unlike the Meta Cloud API, **no public HTTPS endpoint is needed**: Evolution connects *outbound* to WhatsApp, and the webhook travels `evolution → api` inside the compose network. On EC2 the security group only needs SSH (port 22).
   - Evolution's port `8080` is bound to `127.0.0.1` in the compose file. For the one-time admin steps (QR pairing, webhook setup), open an SSH tunnel from your machine and run the curls against it:
     `ssh -L 8080:localhost:8080 <user>@<host>` (on EC2: `ec2-user@<ec2-ip>`, or the Session Manager port-forwarding equivalent).
   - On EC2, use an **x86_64 (amd64)** instance — `t3.medium` (4 GB) minimum; the LLM runs on Ollama Cloud, so no GPU or extra RAM for local models is needed.
   - The api port `8000` is published on localhost by default (`API_BIND`, see *Production hardening* below); keep the security group closed on it unless you also use the Meta webhook or external health checks (the Evolution channel does not need it).

4. **Tuning (optional, see `.env.example`)**

   - `PALMARES_CACHE_TTL_SECONDS` (default `300`) — market data (palmarès) is scraped at most once per TTL and cached in memory + on disk (`app/data/palmares_cache.json`); if a refresh fails, the last good snapshot is served so the bot keeps answering during source outages.
   - `MAX_CONCURRENT_AGENTS` (default `4`) and `AGENT_QUEUE_TIMEOUT` (default `60`) — the Chat API caps concurrent agent runs; extra requests wait, then get a friendly "busy" reply instead of overloading the LLM backend.
   - `API_SECRET_KEY` — **required for production**. The bot must send this shared secret as the `X-API-Key` header; the API rejects unauthenticated calls with 401. If empty, the API runs in dev mode (no auth). Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
   - `RATE_LIMIT_PER_MINUTE` (default `30`) — per-user request limit on `/chat` (0 disables).
   - `DAILY_FREE_QUOTA` (default `30`) — free requests per user per day; over-quota users get a friendly "come back tomorrow" reply. Failed requests are refunded; `QUOTA_EXEMPT_IDS` (comma-separated user ids) bypass the limit. Persisted in SQLite, so restarts don't reset it.
   - **Persistence** (`DATABASE_URL`) — user data (portfolio, tracking, targets, quota, digest subscriptions, score snapshots) and chat checkpoints are backed by SQLAlchemy, with the schema managed by Alembic (`app/db/migrations/`). Empty = local SQLite files in `app/data/` — the zero-config dev default. Set `postgresql://user:password@host:5432/dbname` for PostgreSQL in production (docker compose wires this automatically via `POSTGRES_PASSWORD`). Migrations are applied automatically in Docker (the entrypoint runs them before boot; a schema failure blocks startup) or natively with `python -m scripts.run_migrations`.
     **Local → cloud migration**: point `DATABASE_URL` at the cloud Postgres, run `python -m scripts.run_migrations` (creates/adopts the schema — the initial migration adopts legacy tables in place and never drops them), then restore a plain-SQL dump in the `scripts/backup.sh` format: `pg_dump -U <user> -d <db> > postgres.sql` on the source, `psql "$DATABASE_URL" -f postgres.sql` on the target. There is no SQLite → Postgres data migrator: dev data stays local, production starts fresh (users re-enter portfolios via the bot).
   - `RECURSION_LIMIT` (default `30`) — max agent steps before a partial answer is returned; a weak model looping on a failing tool otherwise burns paid LLM calls.
   - `LLM_REQUEST_TIMEOUT` (default `120` seconds) and `LLM_MAX_RETRIES` (default `1`) — per-request LLM timeout and client-level retry bounds, so a stalled or flaky provider can't pin an agent slot forever (the graph adds at most one more attempt on transient errors).
   - Chat memory: checkpoints live in `app/data/chat_memory.db`, condensed to the last user/answer pairs per thread (`MEMORY_MAX_MESSAGES`, default `20`). Conversations persist across turns so follow-up questions work; threads inactive for more than `MEMORY_TTL_HOURS` (default `24`, `0` = never) are wiped automatically (`MEMORY_CLEANUP_INTERVAL_SEC`, default `3600`). `/clearmemory` clears one user's thread on demand.

   Security notes: portfolio/tracking/alert tools never receive a user id from the model — the identity is injected server-side from the verified chat context, so one user cannot access another user's data. Every reply carries an AI-generated disclaimer. User databases (`app/data/*.db`) are git-ignored and must not be committed.

5. **Tests**

   ```bash
   python tests/test_cache_and_redact.py    # cache + formatting (no deps needed)
   python tests/test_palmares_cache.py      # market-data caching + stale warnings (no deps needed)
   python tests/test_historical_fallback.py # weekend/holiday price lookups (no deps needed)
   python tests/test_scraper_fixtures.py    # golden HTML fixtures for scraper parsers (needs full deps)
   python tests/test_portfolio_auth.py      # security: user-identity injection (needs full deps)
   python tests/test_api_security.py        # security: API key + rate limit (needs full deps)
   python tests/test_daily_quota.py         # free daily quota: limits, refunds, rollover (needs full deps)
   python tests/test_whatsapp_webhook.py    # WhatsApp channel: webhook, dedup, chunking (needs full deps)
   python tests/test_whatsapp_evolution.py  # WhatsApp via Evolution API: webhook, auth, audio (needs full deps)
   python tests/test_graph_e2e.py           # full graph with fake LLM (needs full deps)
   python tests/test_conversation_memory.py # multi-turn memory: clarification persistence, NLU context, TTL cleanup
   python tests/test_postgres_backend.py    # SQL translation always; full PG run when TEST_DATABASE_URL is set
   python tests/test_scoring.py             # deterministic scoring engine: signals, blocks, batch mode (needs full deps)
   python tests/test_advisor_graph.py       # advisor worker routing + tool shapes, fake LLM (needs full deps)
   python tests/test_ohlcv_series.py        # OHLCV Highcharts extraction + CSV round-trip, offline (needs full deps)
   python tests/test_digest.py              # digest subscriptions, composition and job body, temp SQLite (needs full deps)
   ```

   PostgreSQL integration check: `docker compose up -d db`, then
   `TEST_DATABASE_URL=postgresql://brvm:<password>@localhost:5432/brvm python tests/test_postgres_backend.py`.

   **Docker** — the full stack (Chat API + Telegram bot) in one command:

   ```bash
   cp .env.example .env
   # Set TELEGRAM_BOT_TOKEN, API_SECRET_KEY, POSTGRES_PASSWORD
   docker compose build
   docker compose up -d
   ```

   Services: `db` (PostgreSQL 16, data in the `postgres_data` volume), `api` (with
   a `/health` healthcheck), `bot` (waits for the api + db healthchecks), `evolution`
   (self-hosted WhatsApp gateway on port 8080 — see the Evolution section above for
   the one-time QR pairing + webhook setup; if you don't use WhatsApp, comment out
   the `evolution` service AND its `depends_on` entry under `api`). The LLM runs on
   Ollama Cloud (`OLLAMA_CLOUD=true`) — no Ollama container is included in the stack.
   To run on SQLite,
   remove `DATABASE_URL` from the compose services — the `bot_data` volume then
   holds the .db files.

   Note: the `evolution` Postgres database is created by `docker/init-db.sql`, which
   runs only on the **first** initialization of the `postgres_data` volume. On an
   already-initialized volume, create it once manually:
   `docker compose exec db psql -U brvm -d brvm -c "CREATE DATABASE evolution;"`

   On startup each container auto-bootstraps the SGI (broker) list into the shared
   `bot_data` volume (no manual `scripts.run_sgi_fetch` step) and refreshes it when older
   than `SGI_REFRESH_DAYS` (default 7). A manual refresh is one command away:
   `docker compose exec api python -m scripts.run_sgi_fetch`.

## Investment advice (advisor + digest)

The agent answers buy/sell/hold questions through its own ADVISOR worker,
powered by a deterministic scoring engine (`app/services/scoring.py`, pure
Python — no LLM, no invented numbers):

- **Market-wide picks** — « Quelles actions acheter ? », « Top actions BRVM », « Quelles actions vendre/alléger ? »
- **Single stock** — « Faut-il vendre NTLC ? », « Avis sur SLBC », « Garder ou vendre X ? »
- **Portfolio advice** — « Conseil sur mon portefeuille » scores each of your positions (Telegram; the verified identity is injected server-side, like the other portfolio tools).

**How the score is computed**: `0.6 × technicals + 0.4 × fundamentals` → 0-100
→ French signal: **Achat** (≥ 70), **Accumuler** (≥ 55), **Neutre** (≥ 40),
**Alléger** (< 40).

- Technicals: trend (price vs MM50/MM200), momentum (3/6/12-month returns), RSI(14), risk (20-day volatility, 1-year max drawdown, **beta 1 an** when available), volume trend, plus a small adjustment (±4 pts) from **Sika Finance's precomputed technical consensus** (trend/momentum/oscillator/candlestick signals).
- Fundamentals: growth (résultat net + chiffre d'affaires, YoY), valuation (PER vs the BRVM median PER), dividend (**5-year average yield** with a consistency bonus/penalty when the Sika dividend history is available, else latest year).

**Data sources**: daily OHLCV price history scraped from the Rich Bourse chart
pages (`app/data/series/*.csv`, refreshed daily by the timeseries job) and
annual fundamentals from the Sika Finance company fiches
(`app/data/company_details/*.json`, refreshed weekly — societe + COURS + ANALYSE
+ SECTEUR tabs: beta, ranges, dividend history, technical signals, sector
peers). Sika blocks non-browser HTTP clients, so all Sika fetches go through
Tavily extract (`SIKA_TABS_ENABLED=false` saves ~150 Tavily credits/week by
skipping the three extra tabs). The engine only reads
local caches — `score_all` never live-scrapes.

**Limitations (honest)**: no debt or balance-sheet data (not published in a
scrapeable form); fundamentals are annual only, so they lag; the score is a
screening aid, not a crystal ball. Every advice reply and every digest ends
with a disclaimer — this is **not** personalized financial advice.

**Telegram digest** — a scheduled market summary pushed to subscribers:
`/digest jour` (each trading day), `/digest semaine` (weekly), `/digest off`.
Jobs run on weekdays at 18:00 GMT (post-close); the weekly edition goes out
with the Friday daily. Each run scores the whole market once, persists the
snapshots (that is what powers the day-over-day signal changes in "Vos
positions"), then sends the top buy / watch candidates plus the signal changes
of your own portfolio and tracking symbols.

| Env var | Default | Purpose |
| --- | --- | --- |
| `DIGEST_ENABLED` | `true` | Master switch for the scheduled digest jobs |
| `DIGEST_HOUR_GMT` | `18` | Send time (weekdays), GMT — Abidjan trades on GMT |
| `SCORING_TECHNICAL_WEIGHT` | `0.6` | Weight of the technical block in the 0-100 score |
| `SCORING_FUNDAMENTAL_WEIGHT` | `0.4` | Weight of the fundamental block in the 0-100 score |
| `COMPANY_DETAILS_REFRESH_DAYS` | `7` | Max age of the company fiches before re-fetch (entrypoint) |
| `SIKA_TABS_ENABLED` | `true` | Weekly fetch of the Sika COURS/ANALYSE/SECTEUR tabs (beta, technical signals, dividend history, sector peers) via Tavily |

## Production hardening

- **API binding** — the api port is published on `127.0.0.1` by default (`API_BIND`). Set `API_BIND=0.0.0.0` in `.env` only when the Meta WhatsApp webhook (or another external client) must reach the API directly — and then `API_SECRET_KEY` is mandatory. The Telegram bot (outbound polling) and the Evolution gateway (compose network) never need a public port.
- **`API_SECRET_KEY`** — mandatory in production: without it the API runs in dev mode with no authentication (see *Tuning* above).
- **`WHATSAPP_APP_SECRET`** — required for the Meta WhatsApp channel (Meta app → Settings → Basic → App Secret). It verifies the `X-Hub-Signature-256` HMAC on inbound webhooks; the channel stays disabled until it is set.
- **`POSTGRES_PASSWORD`** — no default: `docker compose` fails fast with a clear message until it is set in `.env` (see `.env.example`).
- **Time zone** — `TZ=Africa/Abidjan` is set on the api and bot services (BRVM trades on GMT), so date cutoffs, daily quotas and cache staleness follow the market. Override `TZ` in `.env`.
- **Agent cost safeguards** — `RECURSION_LIMIT` (default `30`) caps agent steps before a partial answer is returned; `LLM_REQUEST_TIMEOUT` (default `120` s) and `LLM_MAX_RETRIES` (default `1`) bound stalled or flaky LLM calls.
- **Log rotation** — every compose service caps Docker's json-file logs (`10m` × 5 files), so container logs can't fill the disk of an always-on host.
- **Non-root containers** — the api/bot image runs as an unprivileged `bot` user; only `/app/app/data` (volume) and the whisper cache are writable.
- **Backups** — `scripts/backup.sh` dumps both Postgres databases and tars the `bot_data` / `evolution_data` volumes into `./backups/<timestamp>/`, pruning backups older than 14 days (override the destination with `BACKUP_DIR`). Schedule it with cron on the Mac mini:

  ```cron
  17 3 * * * cd /path/to/BRVM-stock-ai-agent && ./scripts/backup.sh >> backups/cron.log 2>&1
  ```

  Restore — databases into the running `db` service, volumes with the stack stopped:

  ```bash
  cat backups/<ts>/postgres.sql  | docker compose exec -T db psql -U brvm -d brvm
  cat backups/<ts>/evolution.sql | docker compose exec -T db psql -U brvm -d evolution
  docker run --rm -v <project>_bot_data:/data -v "$PWD/backups/<ts>":/backup alpine sh -c "tar xzf /backup/bot_data.tar.gz -C /data"
  docker run --rm -v <project>_evolution_data:/data -v "$PWD/backups/<ts>":/backup alpine sh -c "tar xzf /backup/evolution_data.tar.gz -C /data"
  ```

  `<project>` is the compose project name (the directory name by default — check with `docker volume ls`). Restoring a dump into an existing database can conflict with rows that are already there; for a clean recovery, restore into a freshly initialized database/volume.
- **External watchdog** — point a monitoring service (e.g. healthchecks.io) at the api's `/health` endpoint, and its cron monitoring at the backup job, so a dead stack or a missed backup alerts you.

## Running the bot where Telegram is blocked (e.g. mainland China)

`api.telegram.org` is unreachable from some networks, and a system-wide VPN on
the host would hijack unrelated services. The fix here routes **only Telegram
traffic** through a Cloudflare Worker reverse proxy — everything else on the
host stays direct.

1. Deploy the worker (free tier is enough; polling ≈ 30k requests/day):

   ```bash
   cd cloudflare/telegram-api-proxy
   npx wrangler login
   npx wrangler deploy        # note the https://<name>.<subdomain>.workers.dev URL
   ```

   (Or paste `worker.js` into a new worker in the Cloudflare dashboard →
   Workers & Pages → Create → edit code.)

2. Set in `.env`:

   ```bash
   TELEGRAM_BASE_URL=https://telegram-api-proxy.<your-subdomain>.workers.dev
   ```

3. Restart the stack (`docker compose up -d`). The bot now polls and sends
   through the worker — including voice-note file downloads
   (`base_file_url` is routed too). Nothing else on the host changes.

Notes:
- The worker only forwards Telegram Bot API path shapes (`/bot<token>/…`,
  `/file/bot<token>/…`) — it is not an open relay. Your token passes through
  in the URL path but is never stored; keep the worker URL private anyway.
- **Groq is not a supported provider**: api.groq.com rejects requests from some
  regions (e.g. mainland China) with `403 Forbidden` before even checking the
  API key — verified unfixable even through a Cloudflare worker (in-region edge
  egress inherits the block). Use OpenRouter and/or Ollama Cloud, which both work.
- WhatsApp note: the Evolution gateway and Meta's `graph.facebook.com` are also
  unreachable from mainland China. The Meta channel's inbound webhooks can
  arrive through your existing Cloudflare setup (tunnel), but outbound sends
  would need the same proxy treatment — ask if you run the WhatsApp channels
  and we'll extend this pattern.

