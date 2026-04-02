"""
J.A.R.V.I.S — Google Gemini Provider
Google Gemini API backend (cloud) via REST API.
"""

import time
import json
import urllib.request
import urllib.error

from core.providers.base import BaseProvider


class GeminiProvider(BaseProvider):
    name = "gemini"
    supports_vision = True

    API_BASE = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, config: dict):
        super().__init__(config)
        gem_cfg = config.get("gemini", {})
        self.api_key = gem_cfg.get("api_key", "")
        self.model = gem_cfg.get("model", "gemini-2.0-flash")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def _build_url(self) -> str:
        return (
            f"{self.API_BASE}/models/{self.model}:generateContent"
            f"?key={self.api_key}"
        )

    def _convert_messages(self, messages: list) -> list:
        """Convert OpenAI-style messages to Gemini contents format."""
        contents = []
        for msg in messages:
            role = msg.get("role", "user")
            # Gemini uses "model" instead of "assistant"
            if role == "assistant":
                role = "model"
            # Skip system messages — handled separately via system_instruction
            if role == "system":
                continue
            contents.append({
                "role": role,
                "parts": [{"text": msg["content"]}],
            })
        return contents

    def _handle_http_error(self, e: urllib.error.HTTPError, context: str = "Gemini"):
        if e.code == 401:
            raise ConnectionError("Gemini API key is invalid.")
        elif e.code == 403:
            raise ConnectionError(
                "Gemini API key lacks permission. "
                "Get a key at https://aistudio.google.dev/apikey"
            )
        elif e.code == 429:
            raise ConnectionError("Rate limit reached.")
        elif e.code == 404:
            raise ConnectionError(
                f"Model '{self.model}' not found. "
                "Check available models at https://ai.google.dev/gemini-api/docs/models"
            )
        raise ConnectionError(f"{context} API error: {e.code}")

    def chat(self, messages: list, system_prompt: str = "",
             max_tokens: int = 2048) -> tuple[str, int]:
        if not self.api_key:
            raise ConnectionError("Gemini API key not configured.")

        payload = {
            "contents": self._convert_messages(messages),
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.7,
            },
        }

        if system_prompt:
            payload["system_instruction"] = {
                "parts": [{"text": system_prompt}],
            }

        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            self._build_url(),
            data=data,
            headers={"Content-Type": "application/json"},
        )

        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                latency = int((time.time() - t0) * 1000)
                reply = result["candidates"][0]["content"]["parts"][0]["text"]
                return reply, latency
        except urllib.error.HTTPError as e:
            self._handle_http_error(e)
        except urllib.error.URLError as e:
            raise ConnectionError(f"Cannot connect to Gemini: {e}")

    def chat_with_image(self, system_prompt: str, image_b64: str,
                        prompt_text: str, max_tokens: int = 1500) -> tuple[str, int]:
        if not self.api_key:
            raise ConnectionError("Gemini API key not configured.")

        payload = {
            "contents": [{
                "role": "user",
                "parts": [
                    {"text": prompt_text},
                    {
                        "inline_data": {
                            "mime_type": "image/png",
                            "data": image_b64,
                        },
                    },
                ],
            }],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "temperature": 0.7,
            },
        }

        if system_prompt:
            payload["system_instruction"] = {
                "parts": [{"text": system_prompt}],
            }

        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            self._build_url(),
            data=data,
            headers={"Content-Type": "application/json"},
        )

        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                latency = int((time.time() - t0) * 1000)
                reply = result["candidates"][0]["content"]["parts"][0]["text"]
                return reply, latency
        except urllib.error.HTTPError as e:
            self._handle_http_error(e, "Gemini vision")
        except urllib.error.URLError as e:
            raise ConnectionError(f"Cannot connect to Gemini: {e}")

    def get_info(self) -> dict:
        return {
            "name": "Google Gemini",
            "model": self.model,
            "vision": True,
            "local": False,
        }
