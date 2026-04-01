"""
J.A.R.V.I.S — OpenAI Provider
OpenAI API backend (cloud). Also works with any OpenAI-compatible API.
"""

import time
import json
import urllib.request
import urllib.error

from core.providers.base import BaseProvider


class OpenAIProvider(BaseProvider):
    name = "openai"
    supports_vision = True

    def __init__(self, config: dict):
        super().__init__(config)
        oai_cfg = config.get("openai", {})
        self.api_key = oai_cfg.get("api_key", "")
        self.model = oai_cfg.get("model", "gpt-4o-mini")
        self.base_url = oai_cfg.get("base_url", "https://api.openai.com")

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: list, system_prompt: str = "",
             max_tokens: int = 2048) -> tuple[str, int]:
        if not self.api_key:
            raise ConnectionError("OpenAI API key not configured.")

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
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency = int((time.time() - t0) * 1000)
                reply = data["choices"][0]["message"]["content"]
                return reply, latency
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ConnectionError("OpenAI API key is invalid.")
            elif e.code == 429:
                raise ConnectionError("Rate limit reached.")
            raise ConnectionError(f"OpenAI API error: {e.code}")
        except urllib.error.URLError as e:
            raise ConnectionError(f"Cannot connect to OpenAI: {e}")

    def chat_with_image(self, system_prompt: str, image_b64: str,
                        prompt_text: str, max_tokens: int = 1500) -> tuple[str, int]:
        if not self.api_key:
            raise ConnectionError("OpenAI API key not configured.")

        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                },
                {"type": "text", "text": prompt_text},
            ],
        }]

        payload = json.dumps({
            "model": self.model,
            "messages": [{"role": "system", "content": system_prompt}] + messages,
            "max_tokens": max_tokens,
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
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency = int((time.time() - t0) * 1000)
                reply = data["choices"][0]["message"]["content"]
                return reply, latency
        except urllib.error.HTTPError as e:
            raise ConnectionError(f"OpenAI vision error: {e.code}")

    def get_info(self) -> dict:
        return {
            "name": "OpenAI",
            "model": self.model,
            "vision": True,
            "local": False,
        }
