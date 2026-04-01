"""
J.A.R.V.I.S — Base Model Provider
Abstract interface that all AI backends must implement.

This makes JARVIS provider-agnostic:
    UI → Brain → Provider Interface → Any Backend
                                       ├─ Anthropic (cloud)
                                       ├─ Ollama (local)
                                       ├─ LM Studio (local)
                                       └─ OpenAI (cloud)
"""

from abc import ABC, abstractmethod


class BaseProvider(ABC):
    """Interface that all model providers must implement."""

    name: str = "base"
    supports_vision: bool = False

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def chat(self, messages: list, system_prompt: str = "",
             max_tokens: int = 2048) -> tuple[str, int]:
        """
        Send messages to the model and get a response.

        Args:
            messages: List of {"role": "user"/"assistant", "content": "..."}
            system_prompt: System instructions
            max_tokens: Max response length

        Returns:
            (response_text, latency_ms)
        """
        raise NotImplementedError

    @abstractmethod
    def chat_with_image(self, system_prompt: str, image_b64: str,
                        prompt_text: str, max_tokens: int = 1500) -> tuple[str, int]:
        """
        Send an image + text to the model (vision).

        Args:
            system_prompt: System instructions
            image_b64: Base64 encoded image
            prompt_text: Text prompt accompanying the image
            max_tokens: Max response length

        Returns:
            (response_text, latency_ms)
        """
        raise NotImplementedError

    def is_available(self) -> bool:
        """Check if this provider is configured and reachable."""
        return True

    def get_info(self) -> dict:
        """Return provider info for display."""
        return {
            "name": self.name,
            "model": "unknown",
            "vision": self.supports_vision,
            "local": False,
        }
