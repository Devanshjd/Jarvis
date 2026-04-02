"""
J.A.R.V.I.S — DeepSeek Provider
DeepSeek cloud API — very capable, very cheap.
OpenAI-compatible API.

Models: deepseek-chat (V3), deepseek-reasoner (R1)
Get key: platform.deepseek.com/api_keys
"""

import time
import json
import urllib.request
import urllib.error

from core.providers.base import BaseProvider


class DeepSeekProvider(BaseProvider):
    name = "deepseek"
    supports_vision = False

    def __init__(self, config: dict):
        super().__init__(config)
        ds_cfg = config.get("deepseek", {})
        self.api_key = ds_cfg.get("api_key", "")
        self.model = ds_cfg.get("model", "deepseek-chat")
        self.base_url = "https://api.deepseek.com"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(self, messages: list, system_prompt: str = "",
             max_tokens: int = 2048) -> tuple[str, int]:
        if not self.api_key:
            raise ConnectionError(
                "DeepSeek API key not configured.\n"
                "Get a key at: platform.deepseek.com/api_keys"
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
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency = int((time.time() - t0) * 1000)
                reply = data["choices"][0]["message"]["content"]
                return reply, latency
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise ConnectionError("DeepSeek API key is invalid.")
            elif e.code == 429:
                raise ConnectionError("DeepSeek rate limit reached.")
            raise ConnectionError(f"DeepSeek API error: {e.code}")
        except urllib.error.URLError as e:
            raise ConnectionError(f"Cannot connect to DeepSeek: {e}")

    def chat_with_image(self, system_prompt: str, image_b64: str,
                        prompt_text: str, max_tokens: int = 1500) -> tuple[str, int]:
        raise ConnectionError(
            "DeepSeek doesn't support vision.\n"
            "Switch to Anthropic, Gemini, or OpenAI for screen scanning."
        )

    def get_info(self) -> dict:
        return {
            "name": "DeepSeek",
            "model": self.model,
            "vision": False,
            "local": False,
        }
