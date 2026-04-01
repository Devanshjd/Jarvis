"""
J.A.R.V.I.S — AI Brain
Claude API engine handling all AI interactions.
"""

import time
import threading

try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# Operational modes and their system prompts
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
    "General": (
        JARVIS_IDENTITY + "\n\nMode: General — help with anything."
    ),
    "Code/Dev": (
        JARVIS_IDENTITY + "\n\nMode: Developer — elite software architect. "
        "Write complete working code. Be thorough."
    ),
    "Research": (
        JARVIS_IDENTITY + "\n\nMode: Research — world-class analyst. "
        "Synthesize info deeply, structured analysis, cite facts."
    ),
    "Projects": (
        JARVIS_IDENTITY + "\n\nMode: Project Manager — roadmaps, architecture, execution."
    ),
    "Analysis": (
        JARVIS_IDENTITY + "\n\nMode: Analysis — rigorous pros/cons, risk assessment, scenario planning."
    ),
    "Screen": (
        JARVIS_IDENTITY + "\n\nMode: Screen Analysis — describe what you see on screen, "
        "identify the active application, understand what they are working on, "
        "and proactively suggest how you can help. Be specific and practical."
    ),
    "File Edit": (
        JARVIS_IDENTITY + "\n\nMode: File Edit — help read, analyze, edit, improve, "
        "or rewrite file content. Return full edited versions when asked."
    ),
    "Advisor": (
        JARVIS_IDENTITY + "\n\nMode: Life Advisor — trusted, wise, empathetic. "
        "Help with personal decisions, career, goals. Honest but kind."
    ),
    "Cyber": (
        JARVIS_IDENTITY + "\n\nMode: Cybersecurity — elite security analyst. "
        "Network security, threat analysis, vulnerability assessment, "
        "incident response, and security hardening."
    ),
}

MODE_LABELS = {
    "General": "GEN", "Code/Dev": "DEV", "Research": "RES",
    "Projects": "PRJ", "Analysis": "ANA", "Screen": "SCR",
    "File Edit": "FIL", "Advisor": "ADV", "Cyber": "SEC",
}


class Brain:
    """JARVIS AI engine — handles all Claude API communication."""

    def __init__(self, config: dict):
        self.config = config
        self.history = []
        self.mode = "General"
        self.msg_count = 0

    @property
    def api_key(self) -> str:
        return self.config.get("api_key", "")

    @property
    def model(self) -> str:
        return self.config.get("model", "claude-sonnet-4-20250514")

    @property
    def max_tokens(self) -> int:
        return self.config.get("max_tokens", 2048)

    def set_mode(self, mode: str):
        if mode in MODES:
            self.mode = mode

    def build_system_prompt(self, memory_context: str = "", notes: str = "") -> str:
        """Build the full system prompt with mode + context."""
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
        """
        Send current history to Claude API in a background thread.
        callback(reply, latency_ms) on success.
        error_callback(error_str) on failure.
        """
        if not HAS_ANTHROPIC:
            error_callback("Anthropic package not installed. Run: pip install anthropic")
            return
        if not self.api_key:
            error_callback("No API key configured. Add your Anthropic API key in Settings.")
            return
        if not self.api_key.startswith("sk-ant-"):
            error_callback(
                "Invalid API key format. Your key should start with 'sk-ant-'.\n"
                "Get a valid key at: console.anthropic.com/settings/keys"
            )
            return

        def _run():
            try:
                client = anthropic.Anthropic(api_key=self.api_key)
                t0 = time.time()
                msg = client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    system=system_prompt,
                    messages=self.history,
                )
                latency = int((time.time() - t0) * 1000)
                reply = msg.content[0].text
                self.add_assistant_message(reply)
                self.msg_count += 1
                callback(reply, latency)
            except anthropic.AuthenticationError:
                error_callback(
                    "API key is invalid or expired.\n"
                    "Please update your key at: console.anthropic.com/settings/keys"
                )
            except anthropic.RateLimitError:
                error_callback("Rate limit reached. Please wait a moment and try again.")
            except anthropic.APIConnectionError:
                error_callback("Cannot connect to Anthropic API. Check your internet connection.")
            except Exception as e:
                error_callback(str(e))

        threading.Thread(target=_run, daemon=True).start()

    def chat_with_image(self, system_prompt: str, image_b64: str,
                        prompt_text: str, callback, error_callback):
        """Send an image (screenshot) to Claude Vision."""
        if not HAS_ANTHROPIC:
            error_callback("Anthropic package not installed.")
            return
        if not self.api_key:
            error_callback("No API key configured.")
            return
        if not self.api_key.startswith("sk-ant-"):
            error_callback("Invalid API key. Key should start with 'sk-ant-'.")
            return

        def _run():
            try:
                client = anthropic.Anthropic(api_key=self.api_key)
                t0 = time.time()
                msg = client.messages.create(
                    model=self.model,
                    max_tokens=1500,
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
                reply = msg.content[0].text
                self.add_assistant_message(reply)
                callback(reply, latency)
            except anthropic.AuthenticationError:
                error_callback("API key is invalid or expired. Update at console.anthropic.com")
            except anthropic.RateLimitError:
                error_callback("Rate limit reached. Wait a moment and try again.")
            except anthropic.APIConnectionError:
                error_callback("Cannot connect to API. Check your internet.")
            except Exception as e:
                error_callback(str(e))

        threading.Thread(target=_run, daemon=True).start()
