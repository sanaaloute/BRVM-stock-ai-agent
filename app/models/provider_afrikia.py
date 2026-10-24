"""Afrikia LLM provider — OpenAI-compatible API (https://afrikia.neobytech.net/v1).

gpt-oss-20b and nemotron-3-nano are reasoning models: the chain-of-thought
comes back as reasoning_content and never leaks into the user-facing content."""
from __future__ import annotations

from typing import Any

import config


def create_afrikia_llm(model: str | None = None, temperature: float = 0, **kwargs: Any):
    from langchain_openai import ChatOpenAI

    model_name = model or config.LLM_MODEL or config.AFRIKIA_MODEL
    api_key = config.AFRIKIA_API_KEY
    if not api_key:
        raise ValueError(
            "AFRIKIA_API_KEY is required for the Afrikia provider. "
            "Set it in .env."
        )

    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        api_key=api_key,
        base_url=config.AFRIKIA_BASE_URL,
        timeout=config.LLM_REQUEST_TIMEOUT,
        max_retries=config.LLM_MAX_RETRIES,
        **kwargs,
    )
