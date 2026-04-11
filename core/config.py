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
        "engine": "classic",       # "classic" (STT+LLM+TTS) or "gemini" (real-time streaming)
        "tts_engine": "auto",      # "auto", "edge", "pyttsx3", "elevenlabs"
        "stt_engine": "auto",      # "auto", "whisper", "google"
        "gemini_voice_name": "Kore",
        "gemini_language_code": "en-US",
    },
    # Provider system — swap AI backends freely
    "provider": "anthropic",       # anthropic, gemini, groq, deepseek, openai, ollama, lmstudio
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
        "live_model": "gemini-2.0-flash-live",  # for real-time voice
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
    "smart_local_recovery": {
        "enabled": True,
        "profile": "gemma",
        "retry_on_uncertain": True,
    },
    "startup_provider": {
        "prefer_local": True,
        "profile": "gemma",
    },
    "screen": {
        "live_interval": 3.0,
        "analysis_interval": 12.0,
        "live_frame_ttl": 5.0,
    },
    "ui": {
        "external_core_window": False,
        "window_geometry": "1280x820",
        "min_width": 960,
        "min_height": 620,
        "enable_global_hide_hotkey": False,
    },
    "presence": {
        "enable_tray": False,
    },
    "auto_repair": {
        "enabled": True,
        "failure_threshold": 3,
        "failure_window_sec": 600,
        "cooldown_sec": 300,
        "max_repairs_per_target": 2,
        "announce_success": True,
    },
    # Local model shortcuts for quick switching
    "local_profiles": {
        "gemma": {
            "provider": "ollama",
            "model": "gemma3:4b",
            "base_url": "http://localhost:11434",
        },
        "gemma_fast": {
            "provider": "ollama",
            "model": "gemma3:1b",
            "base_url": "http://localhost:11434",
        },
        "gemma_vision": {
            "provider": "ollama",
            "model": "gemma3:4b",
            "base_url": "http://localhost:11434",
        },
    },
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
