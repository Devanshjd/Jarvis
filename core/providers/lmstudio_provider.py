"""
J.A.R.V.I.S — LM Studio Provider
Local model backend via LM Studio's OpenAI-compatible API.

Setup:
    1. Download LM Studio: https://lmstudio.ai
    2. Load a model in LM Studio
    3. Start the local server (default: http://localhost:1234)
    4. Set provider to "lmstudio" in JARVIS config
"""

import time
import json
import urllib.request
import urllib.error

from core.providers.base import BaseProvider


class LMStudioProvider(BaseProvider):
    name = "lmstudio"
    supports_vision = False

    def __init__(self, config: dict):
        super().__init__(config)
        lm_cfg = config.get("lmstudio", {})
        self.base_url = lm_cfg.get("base_url", "http://localhost:1234")
        self.model = lm_cfg.get("model", "local-model")

    def is_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/v1/models")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def chat(self, messages: list, system_prompt: str = "",
             max_tokens: int = 2048) -> tuple[str, int]:
        # OpenAI-compatible format
        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)

        payload = json.dumps({
            "model": self.model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                latency = int((time.time() - t0) * 1000)
                reply = data["choices"][0]["message"]["content"]
                return reply, latency
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Cannot connect to LM Studio at {self.base_url}.\n"
                "Make sure the local server is running."
            ) from e
        except (KeyError, IndexError):
            raise ConnectionError("Invalid response from LM Studio.")

    def chat_with_image(self, system_prompt: str, image_b64: str,
                        prompt_text: str, max_tokens: int = 1500) -> tuple[str, int]:
        raise ConnectionError("LM Studio vision not supported yet. Use Anthropic or Ollama+llava.")

    def get_info(self) -> dict:
        return {
            "name": "LM Studio",
            "model": self.model,
            "vision": False,
            "local": True,
            "url": self.base_url,
        }
