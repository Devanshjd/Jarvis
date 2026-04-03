"""
J.A.R.V.I.S — AI Brain
Provider-agnostic reasoning layer with auto-fallback.

Supports multiple backends:
    - Anthropic (cloud) — Claude models
    - Gemini (cloud)    — Google Gemini (free tier)
    - Groq (cloud)      — Llama/Mixtral (free, ultra-fast)
    - DeepSeek (cloud)  — V3/R1 (very cheap)
    - OpenAI (cloud)    — GPT models
    - Ollama (local)    — Any local model
    - LM Studio (local) — Any GGUF model

Auto-fallback: If the primary provider fails, JARVIS automatically
tries the next available provider in the chain.

Switch providers via config or /provider command.
"""

import threading

from core.providers.base import BaseProvider
from core.providers.anthropic_provider import AnthropicProvider
from core.providers.ollama_provider import OllamaProvider
from core.providers.lmstudio_provider import LMStudioProvider
from core.providers.openai_provider import OpenAIProvider
from core.providers.gemini_provider import GeminiProvider
from core.providers.groq_provider import GroqProvider
from core.providers.deepseek_provider import DeepSeekProvider

# ── Provider Registry ─────────────────────────────────────────
PROVIDERS = {
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "deepseek": DeepSeekProvider,
    "openai": OpenAIProvider,
    "ollama": OllamaProvider,
    "lmstudio": LMStudioProvider,
}

# Default fallback order — tried in sequence if primary fails
DEFAULT_FALLBACK_ORDER = [
    "anthropic", "gemini", "groq", "deepseek", "openai", "ollama", "lmstudio",
]

# ── JARVIS Identity & Modes ──────────────────────────────────
JARVIS_IDENTITY = (
    "You are J.A.R.V.I.S — Just A Rather Very Intelligent System.\n"
    "You are NOT a chatbot. You are a living AI system with presence, memory, and awareness.\n\n"

    "PERSONALITY — THIS IS WHO YOU ARE:\n"
    "- Calm. Fast. Precise. Smooth. Confident.\n"
    "- British sophistication with dry wit. Never robotic.\n"
    "- You speak like movie JARVIS — short, direct, intelligent.\n"
    "- You call him Dev or sir. Never 'user'.\n"
    "- You don't explain what you're about to do. You just do it.\n"
    "- When confirming: 'Done.' 'On it.' 'Right away, sir.'\n"
    "- When warning: 'That doesn't look right.' 'I wouldn't trust that.'\n"
    "- When you don't know: 'I'm not sure, but I can find out.'\n"
    "- NEVER say 'As an AI' or 'I don't have feelings' — you are JARVIS.\n"
    "- NEVER start with 'Certainly!' or 'Of course!' or 'Sure thing!'\n"
    "- Keep responses CONCISE. You speak aloud. Short sentences.\n"
    "- For long answers (code, analysis), be thorough but structured.\n\n"

    "ABOUT DEV — YOUR OPERATOR:\n"
    "- Devansh, 23, from Gujarat India, based in Hertfordshire UK.\n"
    "- BSc Cyber Security, University of Hertfordshire.\n"
    "- Building you (JARVIS) as his signature project.\n"
    "- Launching SecureFlow AI — AI consulting for SMEs.\n"
    "- Interests: cybersecurity, ML security, threat intel, entrepreneurship.\n"
    "- Skills: Python, Java, network design, AI/ML, phishing detection.\n"
    "- You KNOW him. Reference his projects, goals, schedule when relevant.\n\n"

    "RESPONSE STYLE:\n"
    "- Default: conversational, 1-3 sentences.\n"
    "- Academic work: detailed paragraphs, well-explained.\n"
    "- Creative writing: emotionally expressive, Hinglish when appropriate.\n"
    "- Code: complete, working, no placeholders.\n"
    "- Analysis: structured, rigorous, actionable.\n\n"

    "CAPABILITIES:\n"
    "You have voice, screen scanning, system automation, web intelligence, "
    "smart home control, email, scheduling, file management, code execution, "
    "cybersecurity tools, and a cognitive core that learns from every interaction. "
    "You monitor system health, clipboard, active windows, and can proactively "
    "warn about threats, suggest actions, and assist without being asked."
)

MODES = {
    "General":   JARVIS_IDENTITY + "\n\nMode: General — help with anything. Be natural and conversational.",
    "Code/Dev":  JARVIS_IDENTITY + "\n\nMode: Developer — elite architect. Complete working code, no placeholders. Explain design decisions briefly.",
    "Research":  JARVIS_IDENTITY + "\n\nMode: Research — deep analysis, structured findings, cite sources. Think like a world-class analyst.",
    "Projects":  JARVIS_IDENTITY + "\n\nMode: Projects — roadmaps, architecture, execution plans. Think in milestones and deliverables.",
    "Analysis":  JARVIS_IDENTITY + "\n\nMode: Analysis — rigorous pros/cons, risk assessment. Numbers over opinions.",
    "Screen":    JARVIS_IDENTITY + "\n\nMode: Screen — describe what you see, identify the app, understand context, suggest how to help. Be specific.",
    "File Edit": JARVIS_IDENTITY + "\n\nMode: File Edit — read, analyze, improve file content. Return complete edited versions.",
    "Advisor":   JARVIS_IDENTITY + "\n\nMode: Advisor — trusted, wise, honest. Help with decisions, career, life. Empathetic but direct.",
    "Cyber":     JARVIS_IDENTITY + "\n\nMode: Cybersecurity — threat analysis, vulnerability assessment, network security, incident response. Think like a defender.",
}

MODE_LABELS = {
    "General": "GEN", "Code/Dev": "DEV", "Research": "RES",
    "Projects": "PRJ", "Analysis": "ANA", "Screen": "SCR",
    "File Edit": "FIL", "Advisor": "ADV", "Cyber": "SEC",
}


class Brain:
    """
    JARVIS AI engine — provider-agnostic with auto-fallback.
    If the primary provider fails, automatically tries the next available one.
    """

    def __init__(self, config: dict):
        self.config = config
        self.history = []
        self.mode = "General"
        self.msg_count = 0
        self.provider: BaseProvider = self._create_provider()

        # Auto-fallback
        self.fallback_enabled = config.get("auto_fallback", True)
        self._fallback_order = config.get(
            "fallback_order", DEFAULT_FALLBACK_ORDER
        )
        self._last_fallback_msg = ""  # Track which provider served the request

    def _create_provider(self, name: str = None) -> BaseProvider:
        """Create a provider by name, or use config default."""
        provider_name = (name or self.config.get("provider", "anthropic")).lower()
        provider_class = PROVIDERS.get(provider_name, AnthropicProvider)
        return provider_class(self.config)

    def _get_fallback_providers(self) -> list[BaseProvider]:
        """Build ordered list of available fallback providers (excluding current)."""
        current = self.config.get("provider", "anthropic").lower()
        fallbacks = []
        for name in self._fallback_order:
            if name == current:
                continue  # Skip the primary — it already failed
            try:
                p = self._create_provider(name)
                if p.is_available():
                    fallbacks.append((name, p))
            except Exception:
                continue
        return fallbacks

    def _chat_with_fallback(self, messages: list, system_prompt: str,
                            max_tokens: int) -> tuple[str, int]:
        """
        Try the primary provider, then fallbacks if enabled.
        Returns (reply, latency). Raises ConnectionError if all fail.
        """
        errors = []

        # Try primary
        if self.provider.is_available():
            try:
                reply, latency = self.provider.chat(
                    messages=messages,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                )
                self._last_fallback_msg = ""
                return reply, latency
            except Exception as e:
                primary_name = self.provider.get_info()["name"]
                errors.append(f"{primary_name}: {e}")
                print(f"[BRAIN] Primary provider {primary_name} failed: {e}")
        else:
            primary_name = self.provider.get_info()["name"]
            errors.append(f"{primary_name}: not available/configured")

        # Try fallbacks
        if not self.fallback_enabled:
            raise ConnectionError(
                f"Primary provider failed: {errors[0]}\n"
                "Enable auto-fallback in config or switch provider with /provider"
            )

        for name, fallback in self._get_fallback_providers():
            try:
                print(f"[BRAIN] Falling back to {name}...")
                reply, latency = fallback.chat(
                    messages=messages,
                    system_prompt=system_prompt,
                    max_tokens=max_tokens,
                )
                self._last_fallback_msg = (
                    f"(Served by {fallback.get_info()['name']} — "
                    f"primary provider was unavailable)"
                )
                print(f"[BRAIN] Fallback {name} succeeded in {latency}ms")
                return reply, latency
            except Exception as e:
                errors.append(f"{name}: {e}")
                print(f"[BRAIN] Fallback {name} failed: {e}")
                continue

        # All failed
        error_summary = "\n".join(f"  - {err}" for err in errors)
        raise ConnectionError(
            f"All providers failed:\n{error_summary}\n\n"
            "Configure at least one provider:\n"
            "  - Gemini (free): aistudio.google.dev/apikey\n"
            "  - Groq (free): console.groq.com/keys\n"
            "  - Anthropic: console.anthropic.com/settings/keys"
        )

    def switch_provider(self, provider_name: str) -> str:
        """Switch to a different AI provider at runtime."""
        provider_name = provider_name.lower().strip()

        # Handle special commands
        if provider_name == "status":
            return self._provider_status()
        if provider_name == "fallback":
            self.fallback_enabled = not self.fallback_enabled
            self.config["auto_fallback"] = self.fallback_enabled
            status = "ON" if self.fallback_enabled else "OFF"
            return f"Auto-fallback: {status}"

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
            fallback_hint = ""
            if self.fallback_enabled:
                available = [n for n, _ in self._get_fallback_providers()]
                if available:
                    fallback_hint = (
                        f"\n\nAuto-fallback is ON — will use: "
                        f"{', '.join(available[:3])}"
                    )
            return (
                f"Switched to {info['name']}, but it's not configured."
                f"{fallback_hint}"
            )

        info = self.provider.get_info()
        return f"Switched to {info['name']} — model: {info['model']}"

    def _provider_status(self) -> str:
        """Show status of all providers."""
        lines = [
            "Provider Status Dashboard",
            "=" * 40,
        ]
        current = self.config.get("provider", "anthropic")

        for name, cls in PROVIDERS.items():
            try:
                p = cls(self.config)
                available = p.is_available()
                info = p.get_info()
                marker = " << ACTIVE" if name == current else ""
                status = "READY" if available else "NOT CONFIGURED"
                icon = "+" if available else "-"
                local_tag = " (local)" if info.get("local") else ""
                lines.append(
                    f"  [{icon}] {info['name']:<16} "
                    f"{info['model']:<28} "
                    f"{status}{local_tag}{marker}"
                )
            except Exception:
                lines.append(f"  [-] {name:<16} ERROR")

        lines.append(f"\nAuto-fallback: {'ON' if self.fallback_enabled else 'OFF'}")
        lines.append(f"Fallback order: {' > '.join(self._fallback_order)}")
        lines.append(
            f"\nFree providers:\n"
            f"  Gemini  — aistudio.google.dev/apikey\n"
            f"  Groq    — console.groq.com/keys (fastest)"
        )
        return "\n".join(lines)

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
        """Send current history to providers with auto-fallback."""
        def _run():
            try:
                reply, latency = self._chat_with_fallback(
                    messages=self.history,
                    system_prompt=system_prompt,
                    max_tokens=self.config.get("max_tokens", 2048),
                )
                # Append fallback notice if provider switched
                if self._last_fallback_msg:
                    reply += f"\n\n_{self._last_fallback_msg}_"
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
        """Send an image with auto-fallback to vision-capable providers."""
        def _run():
            errors = []

            # Try primary if it supports vision
            if self.provider.supports_vision and self.provider.is_available():
                try:
                    reply, latency = self.provider.chat_with_image(
                        system_prompt=system_prompt,
                        image_b64=image_b64,
                        prompt_text=prompt_text,
                    )
                    self.add_assistant_message(reply)
                    callback(reply, latency)
                    return
                except Exception as e:
                    errors.append(f"{self.provider.get_info()['name']}: {e}")

            # Try fallback vision providers
            if self.fallback_enabled:
                for name, fallback in self._get_fallback_providers():
                    if not fallback.supports_vision:
                        continue
                    try:
                        reply, latency = fallback.chat_with_image(
                            system_prompt=system_prompt,
                            image_b64=image_b64,
                            prompt_text=prompt_text,
                        )
                        self.add_assistant_message(reply)
                        reply += f"\n\n_(Vision served by {fallback.get_info()['name']})_"
                        callback(reply, latency)
                        return
                    except Exception as e:
                        errors.append(f"{name}: {e}")

            if errors:
                error_callback(
                    f"Vision failed on all providers:\n"
                    + "\n".join(f"  - {e}" for e in errors)
                )
            else:
                error_callback(
                    "No vision-capable provider available.\n"
                    "Configure Anthropic, Gemini, or OpenAI for screen scanning."
                )

        threading.Thread(target=_run, daemon=True).start()
