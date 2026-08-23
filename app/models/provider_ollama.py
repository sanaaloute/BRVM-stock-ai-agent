"""Ollama LLM provider. Local or Ollama Cloud."""
from __future__ import annotations

from typing import Any

import config


def create_ollama_llm(model: str | None = None, temperature: float = 0, **kwargs: Any):
    from langchain_ollama import ChatOllama

    model_name = model or config.OLLAMA_MODEL
    base_url = config.OLLAMA_BASE_URL
    headers: dict[str, str] | None = None

    if config.OLLAMA_CLOUD:
        if not config.OLLAMA_API_KEY:
            raise ValueError(
                "OLLAMA_API_KEY is required when OLLAMA_CLOUD=true. "
                "Create one at https://ollama.com/settings/keys"
            )
        base_url = config.OLLAMA_CLOUD_HOST
        headers = {"Authorization": f"Bearer {config.OLLAMA_API_KEY}"}
        if not model:
            model_name = config.OLLAMA_CLOUD_MODEL

    # ChatOllama (langchain-ollama 1.1.x) declares no top-level timeout/max_retries
    # or headers fields — unknown kwargs are silently ignored (pydantic
    # extra="ignore"). Timeouts AND the Ollama Cloud Authorization header must go
    # to the underlying ollama/httpx clients via client_kwargs; there is no
    # client-level retry knob (the graph retries transient errors).
    client_kwargs: dict[str, Any] = {"timeout": config.LLM_REQUEST_TIMEOUT}
    if headers:
        client_kwargs["headers"] = headers
    llm_kwargs: dict[str, Any] = {
        "model": model_name,
        "temperature": temperature,
        "keep_alive": _parse_keep_alive(config.OLLAMA_KEEP_ALIVE),
        "client_kwargs": client_kwargs,
        **kwargs,
    }
    # Thinking mode (gpt-oss): "low"/"medium"/"high" effort, or true/false.
    # Reasoning lands in additional_kwargs["reasoning_content"], keeping the
    # answer channel clean.
    reasoning = _parse_reasoning(getattr(config, "OLLAMA_REASONING", ""))
    if reasoning is not None:
        llm_kwargs["reasoning"] = reasoning
    if base_url:
        llm_kwargs["base_url"] = base_url
    return ChatOllama(**llm_kwargs)


def _parse_reasoning(value: str) -> bool | str | None:
    v = (value or "").strip().lower()
    if not v or v in ("none", "off", "0"):
        return None
    if v in ("1", "true", "yes"):
        return True
    if v in ("false", "no"):
        return False
    if v in ("low", "medium", "high"):
        return v
    return None


def _parse_keep_alive(value: str) -> str | int:
    v = (value or "").strip().lower()
    if v in ("0", "0s", "0m", "off"):
        return 0
    return value
