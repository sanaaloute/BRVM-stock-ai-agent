"""Afrikia LLM provider — OpenAI-compatible API (https://afrikia.neobytech.net/v1).

nemotron-3-nano is a reasoning model: the chain-of-thought comes back as
reasoning_content and never leaks into the user-facing content."""
from __future__ import annotations

from typing import Any

import config


_chat_openai_class = None


def _get_chat_openai_class():
    global _chat_openai_class
    if _chat_openai_class is not None:
        return _chat_openai_class
    from langchain_core.messages import AIMessageChunk
    from langchain_openai import ChatOpenAI

    class AfrikiaChatOpenAI(ChatOpenAI):
        """ChatOpenAI that keeps the provider's `reasoning_content` stream
        deltas: stock langchain-openai drops non-standard delta fields. They
        land in AIMessageChunk.additional_kwargs["reasoning_content"] so
        LangGraph (stream_mode="messages") can forward the thinking progress;
        agent nodes strip them before messages reach state/memory."""

        def _convert_chunk_to_generation_chunk(
            self,
            chunk: dict,
            default_chunk_class: type,
            base_generation_info: dict | None,
        ):
            generation_chunk = super()._convert_chunk_to_generation_chunk(
                chunk, default_chunk_class, base_generation_info
            )
            if generation_chunk is not None and isinstance(
                generation_chunk.message, AIMessageChunk
            ):
                choices = chunk.get("choices") or []
                if choices:
                    reasoning = (choices[0].get("delta") or {}).get("reasoning_content")
                    if reasoning:
                        generation_chunk.message.additional_kwargs[
                            "reasoning_content"
                        ] = reasoning
            return generation_chunk

    _chat_openai_class = AfrikiaChatOpenAI
    return _chat_openai_class


def create_afrikia_llm(model: str | None = None, temperature: float = 0, **kwargs: Any):
    model_name = model or config.LLM_MODEL or config.AFRIKIA_MODEL
    api_key = config.AFRIKIA_API_KEY
    if not api_key:
        raise ValueError(
            "AFRIKIA_API_KEY is required for the Afrikia provider. "
            "Set it in .env."
        )

    return _get_chat_openai_class()(
        model=model_name,
        temperature=temperature,
        api_key=api_key,
        base_url=config.AFRIKIA_BASE_URL,
        timeout=config.LLM_REQUEST_TIMEOUT,
        max_retries=config.LLM_MAX_RETRIES,
        **kwargs,
    )
