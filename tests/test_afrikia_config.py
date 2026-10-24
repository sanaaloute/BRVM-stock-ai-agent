"""Afrikia provider config-resolution tests (subprocess-isolated env)."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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
    "api_key": config.AFRIKIA_API_KEY,
    "base_url": config.AFRIKIA_BASE_URL,
    "model": config.AFRIKIA_MODEL,
    "fallback_models": config.AFRIKIA_FALLBACK_MODELS,
    "llm_model": config.LLM_MODEL,
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


def test_afrikia_defaults():
    cfg = read_config()
    assert cfg == {
        "provider": "afrikia",
        "api_key": None,
        "base_url": "https://afrikia.neobytech.net/v1",
        "model": "nemotron-3-nano",
        "fallback_models": "qwen2.5-7b",
        "llm_model": None,
    }


def test_afrikia_env_overrides():
    cfg = read_config(
        AFRIKIA_API_KEY=" sk-test-key ",
        AFRIKIA_BASE_URL="https://afrikia.example.com/v1/",
        AFRIKIA_MODEL="gemma4-e4b",
        AFRIKIA_FALLBACK_MODELS="qwen2.5-7b",
        LLM_MODEL="custom-override",
    )
    assert cfg["api_key"] == "sk-test-key"  # stripped
    assert cfg["base_url"] == "https://afrikia.example.com/v1"  # trailing slash stripped
    assert cfg["model"] == "gemma4-e4b"
    assert cfg["fallback_models"] == "qwen2.5-7b"
    assert cfg["llm_model"] == "custom-override"



