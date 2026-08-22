"""Unified LLM factory. Supports Ollama, Groq, OpenRouter via LLM_PROVIDER env."""
from __future__ import annotations

import threading
from typing import Any

import config

# Chat clients are cached per (provider, model, temperature): building a fresh
# client per request (the NLU node calls get_llm on every message) creates a new
# connection pool each time.
_llm_cache: dict[tuple[str, str, float], Any] = {}
_llm_cache_lock = threading.Lock()


def get_default_model() -> str:
    """Return default model for current LLM_PROVIDER."""
    if config.LLM_MODEL:
        return config.LLM_MODEL
    provider = (config.LLM_PROVIDER or "ollama").strip().lower()
    if provider == "ollama":
        return config.OLLAMA_CLOUD_MODEL if config.OLLAMA_CLOUD else config.OLLAMA_MODEL
    if provider == "groq":
        return config.GROQ_MODEL
    if provider == "openrouter":
        return config.OPENROUTER_MODEL
    return config.OLLAMA_MODEL


def get_llm(model: str | None = None, temperature: float | None = None, **kwargs: Any):
    """
    Return LLM instance based on LLM_PROVIDER (ollama, groq, openrouter).
    Model can be overridden per-call; otherwise uses LLM_MODEL or provider-specific default.
    Temperature defaults to config.LLM_TEMPERATURE (0.0).

    Instances are cached per (provider, model, temperature); callers passing
    extra kwargs always get a fresh, uncached client.
    """
    if temperature is None:
        temperature = config.LLM_TEMPERATURE
    provider = (config.LLM_PROVIDER or "ollama").strip().lower()
    # Use explicit model arg, then LLM_MODEL env, else provider default.
    # In Ollama Cloud mode the local OLLAMA_MODEL tag must not be sent to
    # ollama.com — the cloud model wins unless explicitly overridden.
    ollama_default = (
        config.OLLAMA_CLOUD_MODEL if config.OLLAMA_CLOUD else config.OLLAMA_MODEL
    )
    effective_model = model or config.LLM_MODEL or (
        ollama_default if provider == "ollama" else
        config.GROQ_MODEL if provider == "groq" else
        config.OPENROUTER_MODEL
    )

    if kwargs:
        return _create(provider, effective_model, temperature, **kwargs)
    key = (provider, effective_model, temperature)
    with _llm_cache_lock:
        llm = _llm_cache.get(key)
        if llm is None:
            llm = _create(provider, effective_model, temperature)
            _llm_cache[key] = llm
        return llm


def _create(provider: str, model: str, temperature: float, **kwargs: Any):
    if provider == "ollama":
        return _ollama(model, temperature, **kwargs)
    if provider == "groq":
        return _groq(model, temperature, **kwargs)
    if provider == "openrouter":
        return _openrouter(model, temperature, **kwargs)

    raise ValueError(
        f"Unknown LLM_PROVIDER: {config.LLM_PROVIDER}. "
        "Use: ollama, groq, or openrouter"
    )


def _ollama(model: str | None, temperature: float, **kwargs: Any):
    from .provider_ollama import create_ollama_llm
    return create_ollama_llm(model=model, temperature=temperature, **kwargs)


def _groq(model: str | None, temperature: float, **kwargs: Any):
    from .provider_groq import create_groq_llm
    return create_groq_llm(model=model, temperature=temperature, **kwargs)


def _openrouter(model: str | None, temperature: float, **kwargs: Any):
    from .provider_openrouter import create_openrouter_llm
    return create_openrouter_llm(model=model, temperature=temperature, **kwargs)
