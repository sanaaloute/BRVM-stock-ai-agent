"""Configuration for scrapers, the chat API and the mobile backend."""

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

# set API_BIND=0.0.0.0 only when an external client must reach the API

# directly — and then API_SECRET_KEY is mandatory.

API_BIND = os.getenv("API_BIND", "127.0.0.1").strip() or "127.0.0.1"



# Set BRVM_VERIFY_SSL=0 or false to skip SSL verification for brvm.org (e.g. certificate chain issues)

BRVM_VERIFY_SSL = os.getenv("BRVM_VERIFY_SSL", "true").strip().lower() not in ("0", "false", "no")



# Market data cache: palmarès page is scraped at most once per TTL (stale snapshot

# is served if a refresh fails). Default 300s = 5 minutes.

PALMARES_CACHE_TTL_SECONDS = float(os.getenv("PALMARES_CACHE_TTL_SECONDS", "300"))



# Chat API: cap concurrent agent runs; extra requests wait up to AGENT_QUEUE_TIMEOUT

# then get a friendly "busy" reply instead of melting the LLM backend.

MAX_CONCURRENT_AGENTS = int(os.getenv("MAX_CONCURRENT_AGENTS", "4"))

AGENT_QUEUE_TIMEOUT = float(os.getenv("AGENT_QUEUE_TIMEOUT", "60"))



# Security: shared secret sent as X-API-Key to call the Chat API.

# Empty = dev mode (no auth, warning logged). MUST be set in production.

API_SECRET_KEY = os.getenv("API_SECRET_KEY", "").strip()



# Coarse per-user rate limit on /chat (requests per minute). 0 = disabled.

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "30"))



# Free daily quota on /chat (requests per user per UTC day). 0 = unlimited.

# Failed requests are refunded; rate-limited/busy rejections never count.

DAILY_FREE_QUOTA = int(os.getenv("DAILY_FREE_QUOTA", "30"))

# Comma-separated user ids exempt from the daily quota (owner/testers).

# Accepts mobile user keys like "app:3" or numeric principal ids.

QUOTA_EXEMPT_IDS = {s.strip() for s in os.getenv("QUOTA_EXEMPT_IDS", "").split(",") if s.strip()}



# User database + chat checkpoints. Empty = local SQLite files in app/data/

# (zero config for dev). Set in production / docker compose to use PostgreSQL

# (format: postgresql://user:password@host:5432/dbname).

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()



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



# Afrikia (https://afrikia.neobytech.net/v1) is the only LLM provider used by
# the app — OpenAI-compatible API.
LLM_PROVIDER = "afrikia"

AFRIKIA_API_KEY = os.getenv("AFRIKIA_API_KEY", "").strip() or None
AFRIKIA_BASE_URL = os.getenv("AFRIKIA_BASE_URL", "https://afrikia.neobytech.net/v1").strip().rstrip("/")
AFRIKIA_MODEL = os.getenv("AFRIKIA_MODEL", "gpt-oss-20b").strip() or "gpt-oss-20b"

# Fallback models tried in order (same provider, same key) when the primary
# model's upstream is down.
AFRIKIA_FALLBACK_MODELS = os.getenv("AFRIKIA_FALLBACK_MODELS", "nemotron-3-nano,qwen2.5-7b").strip()

# Optional: override the model for every agent (wins over AFRIKIA_MODEL).
LLM_MODEL = os.getenv("LLM_MODEL", "").strip() or None
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.0").strip() or "0.0")
LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", "120").strip() or "120")
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1").strip() or "1")

# Optional Ollama Cloud key — scraper web_fetch/web_search fallback ONLY
# (app/utils/ollama_web.py, used when Tavily fails). The chat LLM never uses Ollama.
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY", "").strip() or None



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



# Company details cache: entrypoint.sh re-runs scripts/run_company_details_fetch.py when

# any file in $DATA_DIR/company_details/ is missing or older than this many days.

COMPANY_DETAILS_REFRESH_DAYS = int(os.getenv("COMPANY_DETAILS_REFRESH_DAYS", "7").strip() or "7")



# Scoring engine (app/services/scoring.py): block weights for the composite

# 0-100 score. Technicals = trend/momentum/RSI/risk/volume from OHLCV history;

# fundamentals = growth/PER-vs-median/dividend from the cached company fiches.

SCORING_TECHNICAL_WEIGHT = float(os.getenv("SCORING_TECHNICAL_WEIGHT", "0.6").strip() or "0.6")

SCORING_FUNDAMENTAL_WEIGHT = float(os.getenv("SCORING_FUNDAMENTAL_WEIGHT", "0.4").strip() or "0.4")



# Mobile digest: scheduled buy/sell summary pushed (FCM) to subscribers.

# Daily edition on weekdays, weekly on Friday, at DIGEST_HOUR_GMT (post-close).

DIGEST_ENABLED = os.getenv("DIGEST_ENABLED", "true").strip().lower() in ("1", "true", "yes")

DIGEST_HOUR_GMT = int(os.getenv("DIGEST_HOUR_GMT", "18").strip() or "18")



# AI predictions (app/services/predictions.py): daily post-close direction +

# confidence per symbol, served to the mobile app. The LLM only words the

# explanation (PREDICTIONS_LLM_ENABLED=false => deterministic fallback text).

PREDICTIONS_ENABLED = os.getenv("PREDICTIONS_ENABLED", "true").strip().lower() in ("1", "true", "yes")

PREDICTIONS_LLM_ENABLED = os.getenv("PREDICTIONS_LLM_ENABLED", "true").strip().lower() in ("1", "true", "yes")

PREDICTIONS_LLM_CONCURRENCY = int(os.getenv("PREDICTIONS_LLM_CONCURRENCY", "3").strip() or "3")



# --- Mobile app (Flutter) auth & notifications ---

# JWT signing key for mobile user tokens (access/refresh). Empty = mobile auth
# disabled (endpoints return 503). Generate: openssl rand -hex 32
JWT_SECRET = os.getenv("JWT_SECRET", "").strip()

JWT_ACCESS_TTL_SECONDS = int(os.getenv("JWT_ACCESS_TTL_SECONDS", "900").strip() or "900")

JWT_REFRESH_TTL_SECONDS = int(os.getenv("JWT_REFRESH_TTL_SECONDS", str(30 * 24 * 3600)).strip() or str(30 * 24 * 3600))

# OTP codes sent by email (SMTP) or SMS (provider). AUTH_PROVIDER=mock returns
# the code in the API response (dev/tests only, NEVER in production).

AUTH_PROVIDER = os.getenv("AUTH_PROVIDER", "smtp").strip().lower() or "smtp"

# Minimum password length for mobile accounts (email/phone + password).
# Any character mix is accepted (letters, digits, symbols — no case rules).
PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "6").strip() or "6")

OTP_TTL_SECONDS = int(os.getenv("OTP_TTL_SECONDS", "600").strip() or "600")

OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5").strip() or "5")

OTP_RESEND_COOLDOWN_SECONDS = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", "60").strip() or "60")

SMTP_HOST = os.getenv("SMTP_HOST", "").strip()

SMTP_PORT = int(os.getenv("SMTP_PORT", "587").strip() or "587")

SMTP_USER = os.getenv("SMTP_USER", "").strip()

SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()

SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER).strip()

# SMS provider for phone OTP: twilio | none. Account creds below.

SMS_PROVIDER = os.getenv("SMS_PROVIDER", "").strip().lower()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()

TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()

TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "").strip()

# FCM push notifications (Android + iOS). Service-account JSON: either the
# absolute path or the JSON document inline. Empty = push disabled.

FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS", "").strip()



# Sika Finance tab enrichment: the weekly company-details refresh also fetches

# the COURS / ANALYSE / SECTEUR tabs (beta, technical signals, dividend history,

# sector peers) via Tavily (~150 extract credits/week). Set false to save quota.

SIKA_TABS_ENABLED = os.getenv("SIKA_TABS_ENABLED", "true").strip().lower() in ("1", "true", "yes")
