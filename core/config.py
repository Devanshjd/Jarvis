"""
J.A.R.V.I.S — Configuration Manager
Handles loading/saving settings, API keys, and user preferences.
"""

import os
import json

CONFIG_FILE = os.path.expanduser("~/.jarvis_config.json")

DEFAULT_CONFIG = {
    "api_key": "",
    "memories": [],
    "tasks": [],
    "notes": "",
    "voice": {
        "enabled": False,
        "tts_rate": 175,
        "tts_voice": "default",
        "wake_word": "jarvis",
        "listen_timeout": 5,
    },
    # Provider system — swap AI backends freely
    "provider": "anthropic",       # anthropic, ollama, lmstudio, openai
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 2048,
    # Ollama (local)
    "ollama": {
        "base_url": "http://localhost:11434",
        "model": "llama3.2",
    },
    # LM Studio (local)
    "lmstudio": {
        "base_url": "http://localhost:1234",
        "model": "local-model",
    },
    # OpenAI (cloud)
    "openai": {
        "api_key": "",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com",
    },
    # Google Gemini (cloud)
    "gemini": {
        "api_key": "",
        "model": "gemini-2.0-flash",
    },
    # Groq (cloud — free tier, ultra-fast)
    "groq": {
        "api_key": "",
        "model": "llama-3.3-70b-versatile",
    },
    # DeepSeek (cloud — very cheap)
    "deepseek": {
        "api_key": "",
        "model": "deepseek-chat",
    },
    # Auto-fallback: try other providers if primary fails
    "auto_fallback": True,
    "theme": "stark",
}


def load_config() -> dict:
    """Load config from disk, merging with defaults for any missing keys."""
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            saved = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        saved = {}

    # Deep merge defaults with saved config
    config = _deep_merge(DEFAULT_CONFIG, saved)
    return config


def save_config(cfg: dict):
    """Persist config to disk."""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _deep_merge(defaults: dict, overrides: dict) -> dict:
    """Merge overrides into defaults recursively."""
    result = defaults.copy()
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result
