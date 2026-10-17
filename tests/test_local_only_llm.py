import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = "modelscope.cn/Qwen/Qwen3-VL-8B-Instruct-GGUF:Q4_K_M"


def read_config(**overrides):
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONPATH": str(ROOT)}
    env.update(overrides)
    code = """
import json
import dotenv
dotenv.load_dotenv = lambda: None
import config
print(json.dumps({
    "local_only": config.LLM_LOCAL_ONLY,
    "provider": config.LLM_PROVIDER,
    "fallbacks": config.LLM_FALLBACK_PROVIDERS,
    "legacy_fallback": config.LLM_FALLBACK_PROVIDER,
    "cloud": config.OLLAMA_CLOUD,
    "model": config.OLLAMA_MODEL,
    "base_url": config.OLLAMA_BASE_URL,
    "reasoning": config.OLLAMA_REASONING,
}))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_local_only_overrides_legacy_external_settings():
    cfg = read_config(
        LLM_LOCAL_ONLY="true",
        LLM_PROVIDER="openrouter",
        LLM_FALLBACK_PROVIDERS="tokenfree,openrouter",
        LLM_FALLBACK_PROVIDER="tokenfree",
        OLLAMA_CLOUD="true",
        OLLAMA_BASE_URL="https://ollama.com",
        OLLAMA_MODEL="llama3.2:3b",
        OLLAMA_REASONING="high",
    )
    assert cfg == {
        "local_only": True,
        "provider": "ollama",
        "fallbacks": "",
        "legacy_fallback": "",
        "cloud": False,
        "model": DEFAULT_MODEL,
        "base_url": None,
        "reasoning": "",
    }


def test_local_only_accepts_custom_local_settings():
    cfg = read_config(
        OLLAMA_LOCAL_MODEL="nemotron-3-nano:4b",
        OLLAMA_LOCAL_BASE_URL="http://host.docker.internal:11434",
        OLLAMA_LOCAL_REASONING="low",
    )
    assert cfg["provider"] == "ollama"
    assert cfg["cloud"] is False
    assert cfg["model"] == "nemotron-3-nano:4b"
    assert cfg["base_url"] == "http://host.docker.internal:11434"
    assert cfg["reasoning"] == "low"


def test_external_opt_out_preserves_legacy_behavior():
    cfg = read_config(
        LLM_LOCAL_ONLY="false",
        LLM_PROVIDER="openrouter",
        LLM_FALLBACK_PROVIDERS="tokenfree",
        OLLAMA_CLOUD="true",
        OLLAMA_MODEL="qwen3:8b",
        OLLAMA_BASE_URL="https://ollama.com",
        OLLAMA_REASONING="high",
    )
    assert cfg["local_only"] is False
    assert cfg["provider"] == "openrouter"
    assert cfg["fallbacks"] == "tokenfree"
    assert cfg["cloud"] is True
    assert cfg["model"] == "qwen3:8b"
    assert cfg["base_url"] == "https://ollama.com"
    assert cfg["reasoning"] == "high"
