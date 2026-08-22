"""OpenRouter LLM provider. Access multiple models (Claude, GPT, Llama, etc.) via one API."""
from __future__ import annotations

from typing import Any

import config


def create_openrouter_llm(model: str | None = None, temperature: float = 0, **kwargs: Any):
    from langchain_openai import ChatOpenAI

    model_name = model or config.OPENROUTER_MODEL
    api_key = config.OPENROUTER_API_KEY
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY is required for OpenRouter provider. "
            "Get one at https://openrouter.ai/settings/keys"
        )

    llm_kwargs: dict[str, Any] = {
        "api_key": api_key,
        "base_url": "https://openrouter.ai/api/v1",
        "model": model_name,
        "temperature": temperature,
        "timeout": config.LLM_REQUEST_TIMEOUT,
        "max_retries": config.LLM_MAX_RETRIES,
        **kwargs,
    }
    default_headers: dict[str, str] = {}
    if config.OPENROUTER_SITE_URL:
        default_headers["HTTP-Referer"] = config.OPENROUTER_SITE_URL
    if config.OPENROUTER_SITE_NAME:
        default_headers["X-OpenRouter-Title"] = config.OPENROUTER_SITE_NAME
    if default_headers:
        llm_kwargs["default_headers"] = default_headers

    return ChatOpenAI(**llm_kwargs)
