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
    "provider": config.LLM_PROVIDER,
    "fallbacks": config.LLM_FALLBACK_PROVIDERS,
    "legacy_fallback": config.LLM_FALLBACK_PROVIDER,
    "cloud": config.OLLAMA_CLOUD,
    "model": config.OLLAMA_MODEL,
    "base_url": config.OLLAMA_BASE_URL,
    "reasoning": config.OLLAMA_REASONING,
    "keep_alive": config.OLLAMA_KEEP_ALIVE,
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


def test_local_config_ignores_external_and_local_only_settings():
    cfg = read_config(
        LLM_LOCAL_ONLY="false",
        LLM_PROVIDER="openrouter",
        LLM_FALLBACK_PROVIDERS="tokenfree,openrouter",
        LLM_FALLBACK_PROVIDER="tokenfree",
        OLLAMA_CLOUD="true",
        OLLAMA_LOCAL_MODEL="nemotron-3-nano:4b",
        OLLAMA_LOCAL_BASE_URL="http://ignored.example",
        OLLAMA_LOCAL_REASONING="high",
        OLLAMA_LOCAL_KEEP_ALIVE="2m",
        OLLAMA_BASE_URL="https://ollama.com",
        OLLAMA_MODEL="llama3.2:3b",
        OLLAMA_REASONING="high",
    )
    assert cfg == {
        "provider": "ollama",
        "fallbacks": "",
        "legacy_fallback": "",
        "cloud": False,
        "model": "llama3.2:3b",
        "base_url": None,
        "reasoning": "",
        "keep_alive": "24h",
    }


def test_custom_local_settings():
    cfg = read_config(
        OLLAMA_MODEL="nemotron-3-nano:4b",
        OLLAMA_BASE_URL="http://host.docker.internal:11434",
        OLLAMA_KEEP_ALIVE="-1",
    )
    assert cfg["provider"] == "ollama"
    assert cfg["cloud"] is False
    assert cfg["model"] == "nemotron-3-nano:4b"
    assert cfg["base_url"] == "http://host.docker.internal:11434"
    assert cfg["keep_alive"] == "-1"
    assert cfg["reasoning"] == ""


def test_default_model_and_legacy_cloud_endpoint():
    cfg = read_config(OLLAMA_BASE_URL="https://ollama.com/")
    assert cfg["model"] == DEFAULT_MODEL
    assert cfg["base_url"] is None
