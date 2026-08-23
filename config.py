"""Configuration for scrapers and Telegram bot."""

import os

from dotenv import load_dotenv



load_dotenv()



TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")

SLEEP_SECONDS = float(os.getenv("SCRAPER_SLEEP_SECONDS", "2"))



SIKAFINANCE_URL = "https://www.sikafinance.com/"

SIKAFINANCE_PALMARES_URL = "https://www.sikafinance.com/marches/palmares"

RICHBOURSE_URL = "https://www.richbourse.com/common/variation/index"

RICHBOURSE_NEWS_URL = "https://www.richbourse.com/common/news/index"

SIKAFINANCE_BOURSE_URL = "https://www.sikafinance.com/bourse/"

SIKAFINANCE_ACTUALITES_URL = "https://www.sikafinance.com/marches/actualites_bourse_brvm"

SIKAFINANCE_COMMUNIQUES_URL = "https://www.sikafinance.com/marches/communiques_brvm"

RICHBOURSE_PREDICTION_URL = "https://www.richbourse.com/common/prevision-boursiere/synthese"

RICHBOURSE_DIVIDENDE_URL = "https://www.richbourse.com/common/dividende/index"

BRVM_URL = "https://www.brvm.org/"

BRVM_ANNOUNCEMENTS_URL = "https://www.brvm.org/fr/emetteurs/type-annonces/convocations-assemblees-generales"



# Port the Chat API (uvicorn) listens on. Change when 8000 is taken by another service.

API_PORT = int(os.getenv("API_PORT", "8000").strip() or "8000")



# Host interface the API port is published on (docker compose). Default localhost:

# set API_BIND=0.0.0.0 only when the Meta WhatsApp webhook (or another external

# client) must reach the API directly — and then API_SECRET_KEY is mandatory.

API_BIND = os.getenv("API_BIND", "127.0.0.1").strip() or "127.0.0.1"



BRVM_API_URL = os.getenv("BRVM_API_URL", f"http://localhost:{API_PORT}").rstrip("/")

# Set BRVM_VERIFY_SSL=0 or false to skip SSL verification for brvm.org (e.g. certificate chain issues)

BRVM_VERIFY_SSL = os.getenv("BRVM_VERIFY_SSL", "true").strip().lower() not in ("0", "false", "no")



# Market data cache: palmarès page is scraped at most once per TTL (stale snapshot

# is served if a refresh fails). Default 300s = 5 minutes.

PALMARES_CACHE_TTL_SECONDS = float(os.getenv("PALMARES_CACHE_TTL_SECONDS", "300"))



# Chat API: cap concurrent agent runs; extra requests wait up to AGENT_QUEUE_TIMEOUT

# then get a friendly "busy" reply instead of melting the LLM backend.

MAX_CONCURRENT_AGENTS = int(os.getenv("MAX_CONCURRENT_AGENTS", "4"))

AGENT_QUEUE_TIMEOUT = float(os.getenv("AGENT_QUEUE_TIMEOUT", "60"))



# Security: shared secret the bot sends as X-API-Key to call the Chat API.

# Empty = dev mode (no auth, warning logged). MUST be set in production.

API_SECRET_KEY = os.getenv("API_SECRET_KEY", "").strip()



# Coarse per-user rate limit on /chat (requests per minute). 0 = disabled.

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))



# Free daily quota on /chat (requests per user per UTC day). 0 = unlimited.

# Failed requests are refunded; rate-limited/busy rejections never count.

DAILY_FREE_QUOTA = int(os.getenv("DAILY_FREE_QUOTA", "30"))

# Comma-separated user ids exempt from the daily quota (owner/testers).

# Accepts raw Telegram ids or channel keys like "wa:22507000000".

QUOTA_EXEMPT_IDS = {s.strip() for s in os.getenv("QUOTA_EXEMPT_IDS", "").split(",") if s.strip()}



# User database + chat checkpoints. Empty = local SQLite files in app/data/

# (zero config for dev). Set in production / docker compose to use PostgreSQL

# (format: postgresql://user:password@host:5432/dbname).

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()



# WhatsApp Business Cloud API channel. All four required to enable; the webhook

# (GET/POST /whatsapp/webhook) must be reachable over public HTTPS from Meta.

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "").strip()

WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()

WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()

# Meta App Secret (Meta app > Settings > Basic). Used to verify the

# X-Hub-Signature-256 HMAC on inbound webhooks — without it anyone who finds the

# webhook URL can inject messages as any phone number, so the channel stays

# disabled until it is set.

WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "").strip()

WHATSAPP_ENABLED = bool(WHATSAPP_VERIFY_TOKEN and WHATSAPP_ACCESS_TOKEN and WHATSAPP_PHONE_NUMBER_ID and WHATSAPP_APP_SECRET)



# Dedup window for delivered WhatsApp message ids (Meta retries delivery until

# acked, sometimes long after). Default 24h.

WHATSAPP_DEDUP_TTL_SECONDS = float(os.getenv("WHATSAPP_DEDUP_TTL_SECONDS", "86400"))



# WhatsApp via Evolution API channel (self-hosted gateway). All three required

# to enable; the webhook (POST /whatsapp/evolution/webhook) must be reachable

# over public HTTPS from the Evolution instance. EVOLUTION_API_KEY is also used

# to authenticate inbound webhook calls (Evolution sends it as `apikey` header).

EVOLUTION_URL = os.getenv("EVOLUTION_URL", "").strip().rstrip("/")

EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "").strip()

EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "").strip()

EVOLUTION_ENABLED = bool(EVOLUTION_URL and EVOLUTION_API_KEY and EVOLUTION_INSTANCE)



TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")



# Optional: custom base URL for the Telegram Bot API, e.g. a Cloudflare Worker

# reverse proxy (see cloudflare/telegram-api-proxy/) for hosts from which

# api.telegram.org is unreachable. Empty = official https://api.telegram.org.

# Used for both API calls and file downloads (voice notes).

TELEGRAM_BASE_URL = os.getenv("TELEGRAM_BASE_URL", "").strip().rstrip("/")



_raw_symbols = os.getenv("TIMESERIES_SYMBOLS", "").strip()

if _raw_symbols:

    TIMESERIES_SYMBOLS: list[str] = [s.strip().upper() for s in _raw_symbols.split(",") if s.strip()]

else:

    # Default: use all symbols from app/data/BRVM_Companies.xlsx

    try:

        from app.utils.brvm_companies import get_valid_symbols

        TIMESERIES_SYMBOLS = sorted(get_valid_symbols())

    except Exception:

        TIMESERIES_SYMBOLS = []



# LLM provider: ollama | openrouter

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").strip().lower() or "ollama"



# Fallback providers tried in order when the primary's upstream is down

# (502/overload/connection). Ordered, comma-separated. E.g. with

# LLM_PROVIDER=ollama: LLM_FALLBACK_PROVIDERS=tokenfree,openrouter

LLM_FALLBACK_PROVIDERS = os.getenv("LLM_FALLBACK_PROVIDERS", "").strip().lower()

# Legacy single-fallback knob (merged into the chain if set).

LLM_FALLBACK_PROVIDER = os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower()

# Optional: override model for current provider (e.g. LLM_MODEL=llama-3.1-70b)

LLM_MODEL = os.getenv("LLM_MODEL", "").strip() or None

# LLM temperature (0=deterministic, higher=more creative). Default 0.0

LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0").strip() or "0.0")



# Per-request LLM timeout (seconds). Without one, a stalled provider can pin an

# agent slot forever; LLM_MAX_RETRIES bounds client-level retries (the graph

# adds at most one more attempt on transient errors).

LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", "120").strip() or "120")

LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1").strip() or "1")



# Ollama

OLLAMA_CLOUD_HOST = "https://ollama.com"

OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip() or None

OLLAMA_CLOUD = os.getenv("OLLAMA_CLOUD", "").strip().lower() in ("1", "true", "yes")

OLLAMA_CLOUD_MODEL = os.getenv("OLLAMA_CLOUD_MODEL", "gpt-oss:120b").strip() or "gpt-oss:120b"

# Local-only model tag. Ignored when OLLAMA_CLOUD=true (OLLAMA_CLOUD_MODEL wins).

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip() or "llama3.2:3b"

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "").strip() or None

OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "2m").strip() or "2m"



# Voice notes: local faster-whisper transcription (primary; Google Speech fallback).

# small int8 ~250MB download, ~1GB RAM peak, good French accuracy on CPU.

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small").strip() or "small"

WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8").strip() or "int8"




# Graph: max steps before stopping (prevents endless loops; weak models looping

# on a failing tool burn paid LLM calls at 100+)

RECURSION_LIMIT = int(os.getenv("RECURSION_LIMIT", "30").strip() or "30")



# Conversation memory: per-user chat history is kept per thread until the user

# runs /clearmemory, or until it has been inactive for MEMORY_TTL_HOURS

# (0 = never auto-wipe). The cleanup loop runs every MEMORY_CLEANUP_INTERVAL_SEC.

MEMORY_TTL_HOURS = float(os.getenv("MEMORY_TTL_HOURS", "24").strip() or "24")

MEMORY_CLEANUP_INTERVAL_SEC = int(os.getenv("MEMORY_CLEANUP_INTERVAL_SEC", "3600").strip() or "3600")



# Max condensed messages (user + final AI pairs) kept per conversation thread.

MEMORY_MAX_MESSAGES = int(os.getenv("MEMORY_MAX_MESSAGES", "20").strip() or "20")



# TokenFree (https://www.tokenfree.com) — OpenAI-compatible API.

TOKENFREE_API_KEY = os.getenv("TOKENFREE_API_KEY", "").strip()

TOKENFREE_MODEL = os.getenv("TOKENFREE_MODEL", "qwen-max").strip() or "qwen-max"

TOKENFREE_BASE_URL = os.getenv("TOKENFREE_BASE_URL", "https://www.tokenfree.com/v1").strip().rstrip("/")



# OpenRouter (https://openrouter.ai)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip() or None

OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "arcee-ai/trinity-large-preview:free").strip()

OPENROUTER_SITE_URL = os.getenv("OPENROUTER_SITE_URL", "").strip() or None  # Optional: HTTP-Referer for rankings

OPENROUTER_SITE_NAME = os.getenv("OPENROUTER_SITE_NAME", "").strip() or None  # Optional: X-OpenRouter-Title for rankings

# Company details cache: entrypoint.sh re-runs run_company_details_fetch.py when

# any file in $DATA_DIR/company_details/ is missing or older than this many days.

COMPANY_DETAILS_REFRESH_DAYS = int(os.getenv("COMPANY_DETAILS_REFRESH_DAYS", "7").strip() or "7")



# Scoring engine (app/services/scoring.py): block weights for the composite

# 0-100 score. Technicals = trend/momentum/RSI/risk/volume from OHLCV history;

# fundamentals = growth/PER-vs-median/dividend from the cached company fiches.

SCORING_TECHNICAL_WEIGHT = float(os.getenv("SCORING_TECHNICAL_WEIGHT", "0.6").strip() or "0.6")

SCORING_FUNDAMENTAL_WEIGHT = float(os.getenv("SCORING_FUNDAMENTAL_WEIGHT", "0.4").strip() or "0.4")



# Telegram digest: scheduled buy/sell summary pushed to /digest subscribers.

# Daily edition on weekdays, weekly on Friday, at DIGEST_HOUR_GMT (post-close).

DIGEST_ENABLED = os.getenv("DIGEST_ENABLED", "true").strip().lower() in ("1", "true", "yes")

DIGEST_HOUR_GMT = int(os.getenv("DIGEST_HOUR_GMT", "18").strip() or "18")



# Sika Finance tab enrichment: the weekly company-details refresh also fetches

# the COURS / ANALYSE / SECTEUR tabs (beta, technical signals, dividend history,

# sector peers) via Tavily (~150 extract credits/week). Set false to save quota.

SIKA_TABS_ENABLED = os.getenv("SIKA_TABS_ENABLED", "true").strip().lower() in ("1", "true", "yes")
