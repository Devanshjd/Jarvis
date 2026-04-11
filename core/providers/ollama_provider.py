"""
J.A.R.V.I.S — Ollama Provider
Local model backend via Ollama (http://localhost:11434).

Setup:
    1. Install Ollama: https://ollama.com/download
    2. Pull a model: ollama pull llama3.2
    3. Ollama runs automatically on localhost:11434
    4. Set provider to "ollama" in JARVIS config

Recommended models:
    - llama3.2        (8B, good all-round)
    - mistral         (7B, fast and capable)
    - qwen2.5         (7B, strong reasoning)
    - gemma3:4b       (great local-first JARVIS default)
    - gemma3:1b       (faster, lighter)
    - llava           (vision support)
    - deepseek-coder  (coding tasks)
"""

import time
import json
import urllib.request
import urllib.error

from core.providers.base import BaseProvider


class OllamaProvider(BaseProvider):
    name = "ollama"
    supports_vision = False  # Set True if using llava

    def __init__(self, config: dict):
        super().__init__(config)
        ollama_cfg = config.get("ollama", {})
        self.base_url = ollama_cfg.get("base_url", "http://localhost:11434")
        self.model = ollama_cfg.get("model", "llama3.2")

        # Vision models
        vision_models = ["llava", "llava-phi3", "bakllava", "moondream", "gemma3:4b", "gemma3:12b", "gemma3:27b", "gemma3"]
        self.supports_vision = any(v in self.model.lower() for v in vision_models)

    def is_available(self) -> bool:
        """Check if Ollama is running locally."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def chat(self, messages: list, system_prompt: str = "",
             max_tokens: int = 2048) -> tuple[str, int]:
        # Build Ollama message format
        ollama_messages = []
        if system_prompt:
            ollama_messages.append({"role": "system", "content": system_prompt})
        ollama_messages.extend(messages)

        payload = json.dumps({
            "model": self.model,
            "messages": ollama_messages,
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.7,
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency = int((time.time() - t0) * 1000)
                reply = data.get("message", {}).get("content", "")
                if not reply:
                    raise ConnectionError("Empty response from Ollama.")
                return reply, latency
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self.base_url}.\n"
                "Make sure Ollama is running: ollama serve"
            ) from e
        except json.JSONDecodeError:
            raise ConnectionError("Invalid response from Ollama.")

    def chat_with_image(self, system_prompt: str, image_b64: str,
                        prompt_text: str, max_tokens: int = 1500) -> tuple[str, int]:
        if not self.supports_vision:
            raise ConnectionError(
                f"Model '{self.model}' doesn't support vision.\n"
                "Use a vision model: ollama pull llava"
            )

        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": prompt_text,
                    "images": [image_b64],
                },
            ],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency = int((time.time() - t0) * 1000)
                reply = data.get("message", {}).get("content", "")
                return reply, latency
        except urllib.error.URLError as e:
            raise ConnectionError(f"Ollama connection failed: {e}") from e

    def list_models(self) -> list[str]:
        """List locally available Ollama models."""
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def get_info(self) -> dict:
        return {
            "name": "Ollama",
            "model": self.model,
            "vision": self.supports_vision,
            "local": True,
            "url": self.base_url,
        }
