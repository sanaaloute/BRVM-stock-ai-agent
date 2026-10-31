"""Unified LLM factory. All chat traffic goes through the Afrikia provider."""
from __future__ import annotations

import os
import threading
from typing import Any

import config

# Chat clients are cached per (model, temperature, thinking, max_tokens,
# streaming): building a fresh client per request (the NLU node calls get_llm
# on every message) creates a new connection pool each time.
_llm_cache: dict[tuple[str, float, bool, int, bool], Any] = {}
_llm_cache_lock = threading.Lock()

# Per-agent LLM profiles. Reasoning ("thinking") helps agents that analyse
# stocks, portfolios and companies; routing/classification agents stay fast
# (thinking off). max_tokens is always kept >2000: reasoning models think up
# to 1024 tokens (server-side cap) before the final answer starts.
# Per-agent env overrides: LLM_THINKING_<AGENT>=0/1, LLM_MAX_TOKENS_<AGENT>=n.
AGENT_LLM_PROFILES: dict[str, dict[str, Any]] = {
    # Strict-format classification/routing: latency first, no reasoning.
    "nlu": {"thinking": False, "max_tokens": 2048, "streaming": False},
    "supervisor": {"thinking": False, "max_tokens": 2048, "streaming": False},
    # Tool-driven workers with factual, data-shaped answers.
    "scraper": {"thinking": False, "max_tokens": 3072, "streaming": True},
    "timeseries": {"thinking": False, "max_tokens": 2048, "streaming": True},
    "charts": {"thinking": False, "max_tokens": 3072, "streaming": True},
    "news": {"thinking": False, "max_tokens": 3072, "streaming": True},
    "sgi": {"thinking": False, "max_tokens": 3072, "streaming": True},
    "general": {"thinking": False, "max_tokens": 3072, "streaming": True},
    # Analysis & synthesis over stocks/portfolios/companies: reasoning on.
    "analytics": {"thinking": True, "max_tokens": 4096, "streaming": True},
    "portfolio": {"thinking": True, "max_tokens": 4096, "streaming": True},
    "prediction": {"thinking": True, "max_tokens": 4096, "streaming": True},
    "company_details": {"thinking": True, "max_tokens": 4096, "streaming": True},
    # Deepest reasoning: buy/sell/hold investment advice.
    "advisor": {"thinking": True, "max_tokens": 6144, "streaming": True},
}


def _env_bool(name: str) -> bool | None:
    raw = os.getenv(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return None


def _env_int(name: str) -> int | None:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def get_default_model() -> str:
    """Default model: LLM_MODEL env override wins, then AFRIKIA_MODEL."""
    return config.LLM_MODEL or config.AFRIKIA_MODEL


def get_llm(
    model: str | None = None,
    temperature: float | None = None,
    thinking: bool | None = None,
    max_tokens: int | None = None,
    streaming: bool = False,
    **kwargs: Any,
):
    """
    Return a chat client for the Afrikia provider.
    Model can be overridden per-call; otherwise uses LLM_MODEL or AFRIKIA_MODEL.
    Temperature defaults to config.LLM_TEMPERATURE (0.0).
    thinking defaults to config.LLM_THINKING (off): False asks the provider to
    skip the reasoning chain-of-thought (chat_template_kwargs.enable_thinking),
    which cuts latency ~5x on nemotron-3-nano.
    max_tokens defaults to config.LLM_MAX_TOKENS (floor 2048: reasoning models
    think up to 1024 tokens before the answer starts).
    streaming=True makes invoke() stream internally so LangGraph emits the
    model's tokens (stream_mode="messages") to SSE clients.

    Instances are cached per (model, temperature, thinking, max_tokens,
    streaming); callers passing extra kwargs always get a fresh, uncached client.
    """
    if temperature is None:
        temperature = config.LLM_TEMPERATURE
    effective_model = model or get_default_model()
    think = config.LLM_THINKING if thinking is None else thinking
    tokens = max(2048, max_tokens) if max_tokens else config.LLM_MAX_TOKENS

    if kwargs:
        return _create(
            effective_model, temperature, thinking=think,
            max_tokens=tokens, streaming=streaming, **kwargs,
        )
    key = (effective_model, temperature, think, tokens, streaming)
    with _llm_cache_lock:
        llm = _llm_cache.get(key)
        if llm is None:
            llm = _create(
                effective_model, temperature, thinking=think,
                max_tokens=tokens, streaming=streaming,
            )
            _llm_cache[key] = llm
        return llm


def get_agent_llm(
    agent: str,
    model: str | None = None,
    temperature: float | None = None,
    **kwargs: Any,
):
    """Chat client for a named agent, using its AGENT_LLM_PROFILES entry
    (thinking / max_tokens / streaming), overridable via LLM_THINKING_<AGENT>
    and LLM_MAX_TOKENS_<AGENT> env vars. Unknown agents fall back to the
    global defaults (config.LLM_THINKING / config.LLM_MAX_TOKENS)."""
    profile = AGENT_LLM_PROFILES.get(agent) or {}
    tag = agent.upper()

    thinking = _env_bool(f"LLM_THINKING_{tag}")
    if thinking is None:
        thinking = profile.get("thinking")  # None -> get_llm applies config default

    max_tokens = _env_int(f"LLM_MAX_TOKENS_{tag}")
    if max_tokens is None:
        max_tokens = profile.get("max_tokens")

    return get_llm(
        model=model,
        temperature=temperature,
        thinking=thinking,
        max_tokens=max_tokens,
        streaming=bool(profile.get("streaming", False)),
        **kwargs,
    )


def _create(
    model: str,
    temperature: float,
    thinking: bool = True,
    max_tokens: int | None = None,
    streaming: bool = False,
    **kwargs: Any,
):
    from .provider_afrikia import create_afrikia_llm
    if not thinking:
        extra = dict(kwargs.pop("extra_body", None) or {})
        template_kwargs = dict(extra.get("chat_template_kwargs") or {})
        template_kwargs["enable_thinking"] = False
        extra["chat_template_kwargs"] = template_kwargs
        kwargs["extra_body"] = extra
    return create_afrikia_llm(
        model=model, temperature=temperature,
        max_tokens=max_tokens, streaming=streaming, **kwargs,
    )
