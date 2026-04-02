"""
J.A.R.V.I.S — Groq Provider
Groq cloud API — blazing fast inference (free tier available).
OpenAI-compatible API, so we reuse that pattern.

Models: llama-3.3-70b-versatile, mixtral-8x7b-32768, gemma2-9b-it
Get key: console.groq.com/keys
"""

import time
import json
import urllib.request
import urllib.error

from core.providers.base import BaseProvider


class GroqProvider(BaseProvider):
    name = "groq"
    supports_vision = False  # Groq doesn't support vision yet

    def __init__(self, config: dict):
        super().__init__(config)
        groq_cfg = config.get("groq", {})
        self.api_key = groq_cfg.get("api_key", "")
        self.model = groq_cfg.get("model", "llama-3.3-70b-versatile")
        self.base_url = "https://api.groq.com/openai"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: list, system_prompt: str = "",
             max_tokens: int = 2048) -> tuple[str, int]:
        if not self.api_key:
            raise ConnectionError(
                "Groq API key not configured.\n"
                "Get a free key at: console.groq.com/keys"
            )

        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)

        payload = json.dumps({
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )

        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency = int((time.time() - t0) * 1000)
                reply = data["choices"][0]["message"]["content"]
                return reply, latency
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ConnectionError("Groq API key is invalid.")
            elif e.code == 429:
                raise ConnectionError("Groq rate limit reached. Free tier: 30 req/min.")
            elif e.code == 413:
                raise ConnectionError("Request too large for Groq. Try a shorter message.")
            raise ConnectionError(f"Groq API error: {e.code}")
        except urllib.error.URLError as e:
            raise ConnectionError(f"Cannot connect to Groq: {e}")

    def chat_with_image(self, system_prompt: str, image_b64: str,
                        prompt_text: str, max_tokens: int = 1500) -> tuple[str, int]:
        raise ConnectionError(
            "Groq doesn't support vision yet.\n"
            "Switch to Anthropic, Gemini, or OpenAI for screen scanning."
        )

    def get_info(self) -> dict:
        return {
            "name": "Groq",
            "model": self.model,
            "vision": False,
            "local": False,
        }
