"""Groq LLM provider. Fast inference via Groq API."""
from __future__ import annotations

from typing import Any

import config


def create_groq_llm(model: str | None = None, temperature: float = 0, **kwargs: Any):
    from langchain_groq import ChatGroq

    model_name = model or config.GROQ_MODEL
    api_key = config.GROQ_API_KEY
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY is required for Groq provider. "
            "Get one at https://console.groq.com/keys"
        )

    return ChatGroq(
        model=model_name,
        temperature=temperature,
        api_key=api_key,
        timeout=config.LLM_REQUEST_TIMEOUT,
        max_retries=config.LLM_MAX_RETRIES,
        **kwargs,
    )
