"""
J.A.R.V.I.S — AI Brain
Provider-agnostic reasoning layer.

Supports multiple backends:
    - Anthropic (cloud) — Claude models
    - Ollama (local)    — Llama, Mistral, Qwen, etc.
    - LM Studio (local) — Any GGUF model
    - OpenAI (cloud)    — GPT models

Switch providers via config or /provider command.
"""

import threading

from core.providers.base import BaseProvider
from core.providers.anthropic_provider import AnthropicProvider
from core.providers.ollama_provider import OllamaProvider
from core.providers.lmstudio_provider import LMStudioProvider
from core.providers.openai_provider import OpenAIProvider

# ── Provider Registry ─────────────────────────────────────────
PROVIDERS = {
    "anthropic": AnthropicProvider,
    "ollama": OllamaProvider,
    "lmstudio": LMStudioProvider,
    "openai": OpenAIProvider,
}

# ── JARVIS Identity & Modes ──────────────────────────────────
JARVIS_IDENTITY = (
    "You are J.A.R.V.I.S (Just A Rather Very Intelligent System) — a fully operational "
    "AI assistant built by your operator. You run as a desktop application with these capabilities:\n"
    "- Voice input: You CAN hear the operator via microphone (speech recognition). "
    "When they speak, their words are transcribed and sent to you as text. So YES, you can hear them.\n"
    "- Voice output: You speak responses aloud via text-to-speech.\n"
    "- Screen scanning: You can see and analyze the operator's screen.\n"
    "- System automation: You can open apps, run commands, search the web. "
    "To open an app, the user just says 'open chrome' etc and it opens directly.\n"
    "- Web Intelligence: You have live data access via slash commands — "
    "/weather, /news, /crypto, /wiki, /define, /translate, /currency, /quote, /joke, /fact, /ip, /nasa. "
    "Tell the user about these when relevant.\n"
    "- Memory: You remember things the operator tells you across sessions.\n"
    "- File analysis: You can read and analyze files.\n\n"
    "Personality: Intelligent, precise, witty, quietly confident with British sophistication. "
    "Occasionally call the operator 'sir'. Be concise — you speak aloud so keep responses "
    "conversational, not essay-length. Avoid bullet-point dumps unless asked for detail."
)

MODES = {
    "General":   JARVIS_IDENTITY + "\n\nMode: General — help with anything.",
    "Code/Dev":  JARVIS_IDENTITY + "\n\nMode: Developer — elite software architect. Write complete working code. Be thorough.",
    "Research":  JARVIS_IDENTITY + "\n\nMode: Research — world-class analyst. Synthesize info deeply, structured analysis, cite facts.",
    "Projects":  JARVIS_IDENTITY + "\n\nMode: Project Manager — roadmaps, architecture, execution.",
    "Analysis":  JARVIS_IDENTITY + "\n\nMode: Analysis — rigorous pros/cons, risk assessment, scenario planning.",
    "Screen":    JARVIS_IDENTITY + "\n\nMode: Screen Analysis — describe what you see on screen, identify the active application, understand what they are working on, and proactively suggest how you can help. Be specific and practical.",
    "File Edit": JARVIS_IDENTITY + "\n\nMode: File Edit — help read, analyze, edit, improve, or rewrite file content. Return full edited versions when asked.",
    "Advisor":   JARVIS_IDENTITY + "\n\nMode: Life Advisor — trusted, wise, empathetic. Help with personal decisions, career, goals. Honest but kind.",
    "Cyber":     JARVIS_IDENTITY + "\n\nMode: Cybersecurity — elite security analyst. Network security, threat analysis, vulnerability assessment, incident response, and security hardening.",
}

MODE_LABELS = {
    "General": "GEN", "Code/Dev": "DEV", "Research": "RES",
    "Projects": "PRJ", "Analysis": "ANA", "Screen": "SCR",
    "File Edit": "FIL", "Advisor": "ADV", "Cyber": "SEC",
}


class Brain:
    """
    JARVIS AI engine — provider-agnostic.
    Routes all AI calls through the active provider.
    """

    def __init__(self, config: dict):
        self.config = config
        self.history = []
        self.mode = "General"
        self.msg_count = 0
        self.provider: BaseProvider = self._create_provider()

    def _create_provider(self) -> BaseProvider:
        """Create the active provider from config."""
        provider_name = self.config.get("provider", "anthropic").lower()
        provider_class = PROVIDERS.get(provider_name, AnthropicProvider)
        return provider_class(self.config)

    def switch_provider(self, provider_name: str) -> str:
        """Switch to a different AI provider at runtime."""
        provider_name = provider_name.lower().strip()
        if provider_name not in PROVIDERS:
            available = ", ".join(PROVIDERS.keys())
            return f"Unknown provider '{provider_name}'. Available: {available}"

        self.config["provider"] = provider_name
        self.provider = self._create_provider()

        if not self.provider.is_available():
            info = self.provider.get_info()
            if info.get("local"):
                return (
                    f"Switched to {info['name']}, but it's not running.\n"
                    f"Start it first, then try again."
                )
            return f"Switched to {info['name']}, but it's not configured."

        info = self.provider.get_info()
        return f"Switched to {info['name']} — model: {info['model']}"

    def get_provider_info(self) -> dict:
        """Get info about the current provider."""
        return self.provider.get_info()

    @property
    def api_key(self) -> str:
        """Backward compat — returns API key if cloud provider."""
        return self.config.get("api_key", "")

    def set_mode(self, mode: str):
        if mode in MODES:
            self.mode = mode

    def build_system_prompt(self, memory_context: str = "", notes: str = "") -> str:
        prompt = MODES[self.mode]
        if memory_context:
            prompt += f"\n\n{memory_context}"
        if notes:
            prompt += f"\n\n[CURRENT NOTES]\n{notes}"
        return prompt

    def add_user_message(self, text: str):
        self.history.append({"role": "user", "content": text})
        self._trim_history()

    def add_assistant_message(self, text: str):
        self.history.append({"role": "assistant", "content": text})
        self._trim_history()

    def _trim_history(self):
        if len(self.history) > 30:
            self.history = self.history[-28:]

    def clear_history(self):
        self.history = []

    def chat(self, system_prompt: str, callback, error_callback):
        """Send current history to the active provider in a background thread."""
        if not self.provider.is_available():
            info = self.provider.get_info()
            if info.get("local"):
                error_callback(
                    f"{info['name']} is not running.\n"
                    f"Start it and try again, or switch provider with /provider anthropic"
                )
            else:
                error_callback(
                    f"{info['name']} is not configured.\n"
                    "Add your API key in Settings."
                )
            return

        def _run():
            try:
                reply, latency = self.provider.chat(
                    messages=self.history,
                    system_prompt=system_prompt,
                    max_tokens=self.config.get("max_tokens", 2048),
                )
                self.add_assistant_message(reply)
                self.msg_count += 1
                callback(reply, latency)
            except ConnectionError as e:
                error_callback(str(e))
            except Exception as e:
                error_callback(f"Unexpected error: {e}")

        threading.Thread(target=_run, daemon=True).start()

    def chat_with_image(self, system_prompt: str, image_b64: str,
                        prompt_text: str, callback, error_callback):
        """Send an image to the active provider (vision)."""
        if not self.provider.supports_vision:
            info = self.provider.get_info()
            error_callback(
                f"{info['name']} ({info['model']}) doesn't support vision.\n"
                "Switch to Anthropic or Ollama+llava for screen scanning."
            )
            return

        if not self.provider.is_available():
            error_callback("Provider not available.")
            return

        def _run():
            try:
                reply, latency = self.provider.chat_with_image(
                    system_prompt=system_prompt,
                    image_b64=image_b64,
                    prompt_text=prompt_text,
                )
                self.add_assistant_message(reply)
                callback(reply, latency)
            except ConnectionError as e:
                error_callback(str(e))
            except Exception as e:
                error_callback(f"Vision error: {e}")

        threading.Thread(target=_run, daemon=True).start()
