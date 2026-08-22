"""Ollama Cloud model-resolution tests.

Regression guard: when OLLAMA_CLOUD=true the local OLLAMA_MODEL tag must NOT
be sent to ollama.com — OLLAMA_CLOUD_MODEL wins unless the model is explicitly
overridden (per-call arg or LLM_MODEL). ChatOllama is faked (no network).
Run:
    .venv/Scripts/python tests/test_ollama_cloud_resolution.py
"""
import sys
import types
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402


class _FakeChatOllama:
    """Captures the kwargs create_ollama_llm would pass to ChatOllama."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


# create_ollama_llm imports langchain_ollama lazily inside the function, so
# installing the fake into sys.modules before the calls is enough.
_fake = types.ModuleType("langchain_ollama")
_fake.ChatOllama = _FakeChatOllama
sys.modules["langchain_ollama"] = _fake

from app.models.llm import get_default_model, get_llm  # noqa: E402
from app.models.provider_ollama import create_ollama_llm  # noqa: E402

_BASE = {
    "LLM_PROVIDER": "ollama",
    "LLM_MODEL": None,
    "OLLAMA_CLOUD": False,
    "OLLAMA_CLOUD_MODEL": "gpt-oss:120b",
    "OLLAMA_MODEL": "llama3.2:3b",
    "OLLAMA_BASE_URL": None,
    "OLLAMA_API_KEY": None,
}


@contextmanager
def patched_config(**overrides):
    values = dict(_BASE)
    values.update(overrides)
    old = {k: getattr(config, k) for k in values}
    for k, v in values.items():
        setattr(config, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(config, k, v)


def test_cloud_ignores_local_model_tag():
    # The original bug: OLLAMA_MODEL=qwen3:8b set for local use leaked into
    # cloud mode and was sent to ollama.com instead of the cloud model.
    with patched_config(
        OLLAMA_CLOUD=True, OLLAMA_API_KEY="k", OLLAMA_MODEL="qwen3:8b",
        OLLAMA_CLOUD_MODEL="gpt-oss:120b",
    ):
        llm = get_llm()
        assert llm.kwargs["model"] == "gpt-oss:120b", llm.kwargs
        assert get_default_model() == "gpt-oss:120b"
        assert llm.kwargs["base_url"] == config.OLLAMA_CLOUD_HOST, llm.kwargs
        # ChatOllama 1.1.x (pydantic extra="ignore") silently drops unknown
        # top-level kwargs, so the cloud auth header must travel INSIDE
        # client_kwargs — never as a top-level headers= kwarg.
        assert "headers" not in llm.kwargs, llm.kwargs
        client_kwargs = llm.kwargs["client_kwargs"]
        assert client_kwargs["headers"]["Authorization"] == "Bearer k", llm.kwargs
        assert client_kwargs["timeout"] == config.LLM_REQUEST_TIMEOUT, llm.kwargs


def test_cloud_model_env_is_respected():
    with patched_config(
        OLLAMA_CLOUD=True, OLLAMA_API_KEY="k", OLLAMA_CLOUD_MODEL="glm-5.2",
    ):
        assert get_llm().kwargs["model"] == "glm-5.2"


def test_local_mode_uses_ollama_model():
    with patched_config(OLLAMA_CLOUD=False, OLLAMA_MODEL="qwen3:8b"):
        llm = get_llm()
        assert llm.kwargs["model"] == "qwen3:8b", llm.kwargs
        assert get_default_model() == "qwen3:8b"
        assert "headers" not in llm.kwargs, llm.kwargs
        # no auth header inside client_kwargs either in local mode
        assert "headers" not in llm.kwargs["client_kwargs"], llm.kwargs
        assert llm.kwargs["client_kwargs"]["timeout"] == config.LLM_REQUEST_TIMEOUT, llm.kwargs
        assert "base_url" not in llm.kwargs, llm.kwargs


def test_local_mode_default_model():
    with patched_config(OLLAMA_CLOUD=False, OLLAMA_MODEL="llama3.2:3b"):
        assert get_llm().kwargs["model"] == "llama3.2:3b"


def test_llm_model_override_wins_in_cloud():
    with patched_config(
        OLLAMA_CLOUD=True, OLLAMA_API_KEY="k", LLM_MODEL="custom-override",
    ):
        assert get_llm().kwargs["model"] == "custom-override"


def test_explicit_arg_wins_in_cloud():
    with patched_config(OLLAMA_CLOUD=True, OLLAMA_API_KEY="k"):
        assert get_llm(model="explicit-tag").kwargs["model"] == "explicit-tag"


def test_provider_direct_call_uses_cloud_model():
    with patched_config(
        OLLAMA_CLOUD=True, OLLAMA_API_KEY="k", OLLAMA_CLOUD_MODEL="glm-5.2",
        OLLAMA_MODEL="qwen3:8b",
    ):
        assert create_ollama_llm(model=None).kwargs["model"] == "glm-5.2"


def test_provider_direct_call_local():
    with patched_config(OLLAMA_CLOUD=False, OLLAMA_MODEL="qwen3:8b"):
        assert create_ollama_llm(model=None).kwargs["model"] == "qwen3:8b"


def main() -> int:
    tests = [
        test_cloud_ignores_local_model_tag,
        test_cloud_model_env_is_respected,
        test_local_mode_uses_ollama_model,
        test_local_mode_default_model,
        test_llm_model_override_wins_in_cloud,
        test_explicit_arg_wins_in_cloud,
        test_provider_direct_call_uses_cloud_model,
        test_provider_direct_call_local,
    ]
    passed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001
            print(f"FAIL {t.__name__}: {exc}")
        else:
            passed += 1
            print(f"PASS {t.__name__}")
    print(f"{passed}/{len(tests)} passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
