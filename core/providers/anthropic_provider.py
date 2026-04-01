"""
J.A.R.V.I.S — Anthropic Provider
Claude API backend (cloud).
"""

import time
from core.providers.base import BaseProvider

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


class AnthropicProvider(BaseProvider):
    name = "anthropic"
    supports_vision = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.model = config.get("model", "claude-sonnet-4-20250514")

    @property
    def api_key(self) -> str:
        return self.config.get("api_key", "")

    def is_available(self) -> bool:
        return HAS_ANTHROPIC and bool(self.api_key) and self.api_key.startswith("sk-ant-")

    def chat(self, messages: list, system_prompt: str = "",
             max_tokens: int = 2048) -> tuple[str, int]:
        if not HAS_ANTHROPIC:
            raise ConnectionError("Install: pip install anthropic")
        if not self.api_key:
            raise ConnectionError("No API key configured.")
        if not self.api_key.startswith("sk-ant-"):
            raise ConnectionError(
                "Invalid API key format. Should start with 'sk-ant-'.\n"
                "Get a key at: console.anthropic.com/settings/keys"
            )

        client = anthropic.Anthropic(api_key=self.api_key)
        t0 = time.time()
        try:
            msg = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
            )
            latency = int((time.time() - t0) * 1000)
            return msg.content[0].text, latency
        except anthropic.AuthenticationError:
            raise ConnectionError("API key is invalid or expired.")
        except anthropic.RateLimitError:
            raise ConnectionError("Rate limit reached. Wait a moment.")
        except anthropic.APIConnectionError:
            raise ConnectionError("Cannot connect to Anthropic API. Check internet.")

    def chat_with_image(self, system_prompt: str, image_b64: str,
                        prompt_text: str, max_tokens: int = 1500) -> tuple[str, int]:
        if not HAS_ANTHROPIC:
            raise ConnectionError("Install: pip install anthropic")
        if not self.is_available():
            raise ConnectionError("Anthropic not configured.")

        client = anthropic.Anthropic(api_key=self.api_key)
        t0 = time.time()
        try:
            msg = client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": prompt_text},
                    ],
                }],
            )
            latency = int((time.time() - t0) * 1000)
            return msg.content[0].text, latency
        except anthropic.AuthenticationError:
            raise ConnectionError("API key is invalid or expired.")
        except anthropic.RateLimitError:
            raise ConnectionError("Rate limit reached.")
        except anthropic.APIConnectionError:
            raise ConnectionError("Cannot connect to API.")

    def get_info(self) -> dict:
        return {
            "name": "Anthropic",
            "model": self.model,
            "vision": True,
            "local": False,
        }
