"""TokenFree LLM provider. OpenAI-compatible API (https://www.tokenfree.com)."""
from __future__ import annotations

from typing import Any

import config


def create_tokenfree_llm(model: str | None = None, temperature: float = 0, **kwargs: Any):
    from langchain_openai import ChatOpenAI

    model_name = model or config.TOKENFREE_MODEL
    api_key = config.TOKENFREE_API_KEY
    if not api_key:
        raise ValueError(
            "TOKENFREE_API_KEY is required for the TokenFree provider. "
            "Set it in .env (https://www.tokenfree.com)."
        )

    return ChatOpenAI(
        model=model_name,
        temperature=temperature,
        api_key=api_key,
        base_url=config.TOKENFREE_BASE_URL,
        timeout=config.LLM_REQUEST_TIMEOUT,
        max_retries=config.LLM_MAX_RETRIES,
        **kwargs,
    )
