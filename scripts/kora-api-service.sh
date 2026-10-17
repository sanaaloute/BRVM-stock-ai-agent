#!/usr/bin/env bash
# Foreground wrapper for the Kora Bourse mobile API, kept alive by launchd
# (net.neobytech.kbourse.api). Same env as scripts/dev-up.sh.
set -u
cd "$(dirname "$0")/.."

PYTHON=.venv/bin/python
[[ -x "$PYTHON" ]] || PYTHON=python3

# Tavily key comes from .env (needed for the news fallback chain).
TAVILY=$(grep -s '^TAVILY_API_KEY=' .env | cut -d= -f2-)

exec env DATABASE_URL="" \
     JWT_SECRET=dev-mobile-secret-ChangeMe0123456789abcdef \
     AUTH_PROVIDER=mock \
     API_PORT=8002 \
     API_BIND=0.0.0.0 \
     LLM_LOCAL_ONLY=true \
     OLLAMA_LOCAL_BASE_URL= \
     OLLAMA_LOCAL_MODEL=modelscope.cn/Qwen/Qwen3-VL-8B-Instruct-GGUF:Q4_K_M \
     OLLAMA_LOCAL_REASONING= \
     ${TAVILY:+TAVILY_API_KEY=$TAVILY} \
     "$PYTHON" -m scripts.run_api
