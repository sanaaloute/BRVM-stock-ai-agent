"""Unified LLM factory. All chat traffic goes through the Afrikia provider."""
from __future__ import annotations

import threading
from typing import Any

import config

# Chat clients are cached per (model, temperature, thinking): building a fresh
# client per request (the NLU node calls get_llm on every message) creates a
# new connection pool each time.
_llm_cache: dict[tuple[str, float, bool], Any] = {}
_llm_cache_lock = threading.Lock()


def get_default_model() -> str:
    """Default model: LLM_MODEL env override wins, then AFRIKIA_MODEL."""
    return config.LLM_MODEL or config.AFRIKIA_MODEL


def get_llm(
    model: str | None = None,
    temperature: float | None = None,
    thinking: bool | None = None,
    **kwargs: Any,
):
    """
    Return a chat client for the Afrikia provider.
    Model can be overridden per-call; otherwise uses LLM_MODEL or AFRIKIA_MODEL.
    Temperature defaults to config.LLM_TEMPERATURE (0.0).
    thinking defaults to config.LLM_THINKING (off): False asks the provider to
    skip the reasoning chain-of-thought (chat_template_kwargs.enable_thinking),
    which cuts latency ~5x on nemotron-3-nano.

    Instances are cached per (model, temperature, thinking); callers passing
    extra kwargs always get a fresh, uncached client.
    """
    if temperature is None:
        temperature = config.LLM_TEMPERATURE
    effective_model = model or get_default_model()
    think = config.LLM_THINKING if thinking is None else thinking

    if kwargs:
        return _create(effective_model, temperature, thinking=think, **kwargs)
    key = (effective_model, temperature, think)
    with _llm_cache_lock:
        llm = _llm_cache.get(key)
        if llm is None:
            llm = _create(effective_model, temperature, thinking=think)
            _llm_cache[key] = llm
        return llm


def _create(model: str, temperature: float, thinking: bool = True, **kwargs: Any):
    from .provider_afrikia import create_afrikia_llm
    if not thinking:
        extra = dict(kwargs.pop("extra_body", None) or {})
        template_kwargs = dict(extra.get("chat_template_kwargs") or {})
        template_kwargs["enable_thinking"] = False
        extra["chat_template_kwargs"] = template_kwargs
        kwargs["extra_body"] = extra
    return create_afrikia_llm(model=model, temperature=temperature, **kwargs)
