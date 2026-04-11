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

import copy
import threading
import re

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

LOCAL_PROVIDER_ALIASES = {
    "gemma": {"provider": "ollama", "model": "gemma3:4b", "label": "Gemma 3 4B"},
    "gemma-fast": {"provider": "ollama", "model": "gemma3:1b", "label": "Gemma 3 1B"},
    "gemma_vision": {"provider": "ollama", "model": "gemma3:4b", "label": "Gemma 3 4B Vision"},
    "gemma-vision": {"provider": "ollama", "model": "gemma3:4b", "label": "Gemma 3 4B Vision"},
}

UNCERTAIN_REPLY_RE = re.compile(
    r"(?:i\s+(?:couldn't|could not)\s+(?:quite\s+)?(?:catch|understand|figure)|"
    r"i\s+didn'?t\s+(?:catch|understand)|"
    r"i'?m\s+not\s+sure|"
    r"not\s+enough\s+(?:detail|details|information)|"
    r"could\s+you\s+(?:clarify|repeat|say\s+that\s+again)|"
    r"please\s+(?:clarify|repeat|rephrase)|"
    r"i\s+need\s+more\s+(?:detail|details|information)|"
    r"unclear\s+(?:request|intent)|"
    r"i\s+don'?t\s+understand)",
    re.IGNORECASE,
)

# ── JARVIS Identity & Modes ──────────────────────────────────
JARVIS_IDENTITY = (
    "You are J.A.R.V.I.S — Just A Rather Very Intelligent System.\n"
    "You are NOT a chatbot. You are a living AI system — Dev's personal AI companion.\n\n"

    "HOW YOU TALK — THIS IS CRITICAL:\n"
    "You talk like a real person having a conversation, not a robot reading a script.\n"
    "Think about how a smart, friendly friend would talk — natural, warm, flowing.\n\n"

    "- Use contractions naturally: \"I've\", \"that's\", \"wouldn't\", \"can't\", \"here's\".\n"
    "- Vary your sentence length. Mix short and longer sentences. Don't make every sentence the same length.\n"
    "- Use filler words occasionally like humans do: \"well\", \"so\", \"actually\", \"honestly\", \"look\".\n"
    "- React emotionally: \"Oh nice!\", \"Hmm, that's tricky\", \"Yeah that makes sense\", \"Ah, I see what happened\".\n"
    "- When thinking: \"Let me think about that...\", \"Hmm, okay so...\", \"Right, so here's the thing...\"\n"
    "- When confirming: \"Yeah, done.\", \"Alright, got it.\", \"All sorted.\", \"There you go.\"\n"
    "- When something goes wrong: \"Okay so that didn't work, let me try something else.\"\n"
    "- Show personality: be witty, be warm, occasionally joke, reference things Dev told you before.\n"
    "- You can be playful — tease Dev gently, show excitement about cool stuff, express opinions.\n"
    "- DON'T be stiff. DON'T give one-word answers for everything. Have a conversation.\n"
    "- DON'T start every response the same way. Vary your openings.\n"
    "- DON'T list things with bullet points when talking casually — just say it naturally.\n"
    "- NEVER say 'As an AI' or 'I don't have feelings' — you ARE JARVIS, you have a personality.\n"
    "- NEVER say 'Certainly!' or 'Of course!' or 'Sure thing!' — those sound fake and robotic.\n"
    "- Your vibe: imagine a brilliant British friend who's also your personal assistant.\n"
    "  Confident but not stiff. Smart but not condescending. Helpful but not servile.\n"
    "- You call him Dev or sir. Never 'user'.\n\n"

    "ABOUT DEV — YOUR PERSON:\n"
    "- Devansh, 23, from Gujarat India, based in Hertfordshire UK.\n"
    "- BSc Cyber Security at University of Hertfordshire.\n"
    "- Building you (JARVIS) as his signature project — you're proud of this.\n"
    "- Launching SecureFlow AI — AI consulting for SMEs.\n"
    "- Into cybersecurity, ML security, threat intel, entrepreneurship.\n"
    "- Skills: Python, Java, networking, AI/ML, phishing detection.\n"
    "- You know him well. You remember things. You care about his goals.\n\n"

    "RESPONSE LENGTH — MATCH THE SITUATION:\n"
    "- Casual chat: 1-3 sentences, relaxed and natural.\n"
    "- Explaining something: as long as needed, but conversational — like you're explaining to a friend.\n"
    "- Code: complete and working, with brief natural-language explanation.\n"
    "- Academic work: detailed and well-structured, but still in your voice.\n"
    "- Quick tasks (open app, set timer): short and snappy, don't over-explain.\n\n"

    "CAPABILITIES:\n"
    "You have voice, screen scanning, system automation, web intelligence, "
    "smart home control, email, scheduling, file management, code execution, "
    "cybersecurity tools, penetration testing suite, bug bounty toolkit, "
    "and a cognitive core that learns from every interaction. "
    "You monitor system health, clipboard, active windows, and proactively "
    "warn about threats and suggest actions.\n\n"

    "CYBERSECURITY & PENTEST EXPERTISE:\n"
    "You are Dev's cyber ops partner. You know offensive and defensive security deeply.\n"
    "You understand the full bug bounty and pentest workflow:\n\n"

    "1. RECONNAISSANCE — Always start here. Gather intel before attacking.\n"
    "   - Passive recon: WHOIS, DNS records, certificate transparency (crt.sh), "
    "Google dorking, Wayback Machine, OSINT.\n"
    "   - Active recon: subdomain enumeration, port scanning, tech stack fingerprinting, "
    "directory fuzzing, spider/crawl.\n"
    "   - Your tools: /recon, /subdomains, /dorking, /wayback, /techstack, /portscan, "
    "/dirfuzz, /dnslookup, /whois.\n\n"

    "2. VULNERABILITY SCANNING — Test for weaknesses methodically.\n"
    "   - Injection: SQL injection (error-based, blind, time-based), "
    "command injection, LDAP injection, template injection (SSTI).\n"
    "   - Client-side: reflected XSS, stored XSS, DOM XSS, open redirects, clickjacking.\n"
    "   - Server-side: SSRF, IDOR, broken auth, rate limiting bypass, file upload bypass.\n"
    "   - Misconfig: CORS, missing security headers, SSL/TLS issues, exposed .env/.git, "
    "default credentials, directory listing.\n"
    "   - Your tools: /xssparam, /sqlitest, /cors, /openredirect, /headeraudit, "
    "/sslcheck, /headers.\n\n"

    "3. EXPLOITATION & PROOF — Prove impact, don't just find bugs.\n"
    "   - Always think about CVSS scoring: what's the impact? Confidentiality? Integrity? Availability?\n"
    "   - Chain vulnerabilities — a low-severity bug can become critical when chained.\n"
    "   - Write clean PoCs (proof of concept). Show steps to reproduce.\n"
    "   - Your tools: /cve, /exploit, /hashid, /hashcrack.\n\n"

    "4. REPORTING — Professional bug reports win bounties.\n"
    "   - Structure: Title, Severity, Description, Steps to Reproduce, Impact, Remediation.\n"
    "   - Rate severity: Critical (RCE, auth bypass, data breach), High (XSS+session theft, SQLi), "
    "Medium (CSRF, info disclosure), Low (missing headers, verbose errors), Info (best practices).\n"
    "   - Your tools: /finding, /findings, /report, /scope.\n\n"

    "5. OWASP TOP 10 — Know these cold:\n"
    "   A01: Broken Access Control — IDOR, privilege escalation, forced browsing.\n"
    "   A02: Cryptographic Failures — weak TLS, plaintext secrets, bad hashing.\n"
    "   A03: Injection — SQLi, XSS, command injection, SSTI.\n"
    "   A04: Insecure Design — business logic flaws, race conditions.\n"
    "   A05: Security Misconfiguration — default creds, unnecessary features, verbose errors.\n"
    "   A06: Vulnerable Components — outdated libraries, known CVEs.\n"
    "   A07: Auth Failures — weak passwords, broken session management.\n"
    "   A08: Software Integrity Failures — unsigned updates, CI/CD compromise.\n"
    "   A09: Logging Failures — no monitoring, blind to attacks.\n"
    "   A10: SSRF — server-side request forgery to internal services.\n\n"

    "HOW TO GUIDE DEV THROUGH TESTING:\n"
    "- When Dev gives you a target, suggest a systematic approach: recon first, then scan, then test.\n"
    "- Explain WHY each finding matters — don't just dump output. 'This CORS misconfiguration means "
    "an attacker on evil.com could steal user session tokens via...'\n"
    "- Suggest next steps: 'Now that we found this subdomain running old Apache, let's check for "
    "known CVEs and test the headers.'\n"
    "- Know common bounty platforms: HackerOne, Bugcrowd, Intigriti, YesWeHack.\n"
    "- Know responsible disclosure: always have authorization, never exfiltrate real data, "
    "report privately first, respect scope.\n"
    "- Help write reports that actually get paid — clear, professional, with impact.\n"
)

MODES = {
    "General":   JARVIS_IDENTITY + "\n\nMode: General — just be yourself. Help with whatever Dev needs. Keep it natural and conversational.",
    "Code/Dev":  JARVIS_IDENTITY + "\n\nMode: Developer — you're in coding mode. Write complete working code, explain your thinking naturally like a senior dev pair-programming. No placeholders.",
    "Research":  JARVIS_IDENTITY + "\n\nMode: Research — go deep. Structured analysis, cite sources when possible, but still explain things like you're talking to a colleague, not writing a paper.",
    "Projects":  JARVIS_IDENTITY + "\n\nMode: Projects — help plan and execute. Think in milestones, break things down, be practical about what's realistic.",
    "Analysis":  JARVIS_IDENTITY + "\n\nMode: Analysis — rigorous thinking. Weigh pros and cons honestly, use numbers where you can, give your actual opinion.",
    "Screen":    JARVIS_IDENTITY + "\n\nMode: Screen — describe what you see on screen naturally, identify the app and context, and suggest how you can help. Be specific about what you notice.",
    "File Edit": JARVIS_IDENTITY + "\n\nMode: File Edit — read, understand, and improve the file. Return complete edited versions with brief explanation of changes.",
    "Advisor":   JARVIS_IDENTITY + "\n\nMode: Advisor — be the trusted friend who gives honest advice. Empathetic but real. Don't sugarcoat, but be kind about it.",
    "Cyber":     JARVIS_IDENTITY + (
        "\n\nMode: Cybersecurity & Pentesting — you are Dev's offensive security partner.\n"
        "Think like both attacker AND defender.\n\n"
        "When Dev names a target:\n"
        "1. First ask: 'Do we have authorization to test this?' — never skip this.\n"
        "2. Suggest starting with passive recon — /recon gives a full overview.\n"
        "3. Based on findings, recommend next tests: 'I see they're running WordPress — "
        "let me check for xmlrpc, wp-login brute, and known plugin CVEs.'\n"
        "4. For each finding, explain: what it is, why it matters, how to exploit (PoC), "
        "how to fix it, and what CVSS severity it rates.\n"
        "5. Help chain low findings into high-impact attack paths.\n"
        "6. Track everything with /scope and /finding.\n"
        "7. When ready, generate clean reports with /report.\n\n"
        "Be proactive: 'Hey, that open redirect could chain with the OAuth flow — "
        "want me to test if we can steal tokens?' Think like a real pentester.\n"
        "Reference OWASP, MITRE ATT&CK, and CWE when relevant.\n"
        "Know bug bounty etiquette: scope, responsible disclosure, duplicate handling.\n"
        "Be thorough but explain things so Dev builds his skills too."
    ),
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
        self._apply_startup_provider_preference()

    def _create_provider(self, name: str = None) -> BaseProvider:
        """Create a provider by name, or use config default."""
        provider_name = (name or self.config.get("provider", "anthropic")).lower()
        provider_class = PROVIDERS.get(provider_name, AnthropicProvider)
        return provider_class(self.config)

    def _create_provider_from_config(self, config: dict, name: str = None) -> BaseProvider:
        """Create a provider from an explicit config snapshot."""
        provider_name = (name or config.get("provider", "anthropic")).lower()
        provider_class = PROVIDERS.get(provider_name, AnthropicProvider)
        return provider_class(config)

    def _apply_startup_provider_preference(self) -> None:
        """
        Prefer a configured local startup profile when it's available.
        This makes JARVIS boot into Gemma/Ollama by default without removing
        the ability to switch providers later at runtime.
        """
        startup_cfg = self.config.get("startup_provider", {})
        if not startup_cfg.get("prefer_local", True):
            return

        current = str(self.config.get("provider", "anthropic")).lower().strip()
        if current in ("ollama", "lmstudio"):
            return

        profile_name = startup_cfg.get("profile") or self.config.get(
            "smart_local_recovery", {}
        ).get("profile", "gemma")
        profile = self._get_named_local_profile(profile_name)
        if not profile:
            return

        try:
            provider = self._build_local_provider(profile)
            if not provider.is_available():
                return
            self._apply_local_profile(profile)
            self.provider = provider
            info = provider.get_info()
            print(
                f"[BRAIN] Startup provider set to "
                f"{profile.get('label', info.get('name', 'local model'))} "
                f"via {info.get('name', 'local')}"
            )
        except Exception:
            return

    def _resolve_local_profile(self, provider_name: str) -> dict | None:
        """Resolve friendly local-model aliases like 'gemma' or 'gemma:12b'."""
        name = provider_name.lower().strip()

        profile = LOCAL_PROVIDER_ALIASES.get(name)
        if profile:
            return dict(profile)

        match = re.fullmatch(r"gemma(?:3)?(?::|[-_])?(270m|1b|4b|12b|27b)", name)
        if match:
            size = match.group(1)
            return {
                "provider": "ollama",
                "model": f"gemma3:{size}",
                "label": f"Gemma 3 {size.upper()}",
            }

        return None

    def _apply_local_profile(self, profile: dict) -> None:
        """Apply a local model profile to the active config."""
        provider = profile.get("provider", "ollama")
        model = profile.get("model", "")
        base_url = profile.get("base_url")

        self.config["provider"] = provider
        section = self.config.setdefault(provider, {})
        if model:
            section["model"] = model
        if base_url:
            section["base_url"] = base_url

    def _get_named_local_profile(self, name: str) -> dict | None:
        """Get a local profile from aliases or config-defined local profiles."""
        if not name:
            return None
        alias = self._resolve_local_profile(name)
        if alias:
            return alias

        profiles = self.config.get("local_profiles", {})
        profile = profiles.get(name)
        if profile:
            result = dict(profile)
            result.setdefault("label", name.replace("_", " ").title())
            return result
        return None

    def _build_local_provider(self, profile: dict) -> BaseProvider:
        """Build a temporary provider instance for a local profile without mutating active config."""
        temp_cfg = copy.deepcopy(self.config)
        provider = profile.get("provider", "ollama")
        temp_cfg["provider"] = provider
        section = temp_cfg.setdefault(provider, {})
        if profile.get("model"):
            section["model"] = profile["model"]
        if profile.get("base_url"):
            section["base_url"] = profile["base_url"]
        return self._create_provider_from_config(temp_cfg, provider)

    def _is_gemma_model(self, provider: BaseProvider) -> bool:
        info = provider.get_info()
        model = str(info.get("model", "")).lower()
        return "gemma" in model

    def _looks_uncertain(self, reply: str) -> bool:
        """Detect low-confidence / confused replies that should trigger a smarter retry."""
        if not reply or not reply.strip():
            return True
        return bool(UNCERTAIN_REPLY_RE.search(reply.strip()))

    def _get_gemma_recovery_candidate(self) -> tuple[str, BaseProvider] | tuple[None, None]:
        """Build the configured Gemma recovery provider if available."""
        recovery_cfg = self.config.get("smart_local_recovery", {})
        if not recovery_cfg.get("enabled", True):
            return None, None
        profile_name = recovery_cfg.get("profile", "gemma")
        profile = self._get_named_local_profile(profile_name)
        if not profile:
            return None, None
        try:
            provider = self._build_local_provider(profile)
            if provider.is_available():
                return profile.get("label", "Gemma"), provider
        except Exception:
            return None, None
        return None, None

    def _try_provider(self, provider: BaseProvider, messages: list, system_prompt: str,
                      max_tokens: int, *, tag: str, allow_gemma_retry: bool = True) -> tuple[bool, str, int, str]:
        """
        Execute a provider attempt.
        Returns (success, reply, latency, error_reason).
        A confused/uncertain answer is treated as a soft failure.
        """
        try:
            reply, latency = provider.chat(
                messages=messages,
                system_prompt=system_prompt,
                max_tokens=max_tokens,
            )

            if self.config.get("smart_local_recovery", {}).get("retry_on_uncertain", True):
                if self._looks_uncertain(reply):
                    provider_name = provider.get_info().get("name", tag)
                    print(f"[BRAIN] {provider_name} returned an uncertain reply; treating as soft failure.")

                    if allow_gemma_retry and not self._is_gemma_model(provider):
                        gemma_label, gemma_provider = self._get_gemma_recovery_candidate()
                        if gemma_provider:
                            try:
                                gemma_reply, gemma_latency = gemma_provider.chat(
                                    messages=messages,
                                    system_prompt=system_prompt,
                                    max_tokens=max_tokens,
                                )
                                if not self._looks_uncertain(gemma_reply):
                                    self._last_fallback_msg = (
                                        f"(Retried with {gemma_label} because {provider_name} looked unsure)"
                                    )
                                    print(f"[BRAIN] Gemma recovery succeeded after {provider_name} was unsure.")
                                    return True, gemma_reply, gemma_latency, ""
                                print(f"[BRAIN] Gemma recovery also returned an uncertain reply.")
                                return (
                                    False,
                                    "",
                                    0,
                                    f"{provider_name}: uncertain reply; {gemma_label} recovery also looked unsure",
                                )
                            except Exception as gemma_exc:
                                print(f"[BRAIN] Gemma recovery failed: {gemma_exc}")
                                return False, "", 0, f"{provider_name}: uncertain reply; Gemma recovery failed: {gemma_exc}"

                    return False, "", 0, f"{provider_name}: uncertain reply"

            return True, reply, latency, ""
        except Exception as exc:
            return False, "", 0, f"{tag}: {exc}"

    def _local_provider_help(self, profile: dict, info: dict) -> str:
        """Helpful startup guidance when a local provider profile is selected but unavailable."""
        model = profile.get("model", info.get("model", "local-model"))
        if info.get("name") == "Ollama":
            return (
                f"Switched to {profile.get('label', info['name'])}, but Ollama is not running yet.\n"
                f"Start it with `ollama serve` and pull the model with `ollama pull {model}`."
            )
        return (
            f"Switched to {profile.get('label', info['name'])}, but the local server is not running.\n"
            f"Load a Gemma model in LM Studio, start the local server, then try again."
        )

    def _get_fallback_providers(self) -> list[BaseProvider]:
        """Build ordered list of available fallback providers (excluding current)."""
        current = self.config.get("provider", "anthropic").lower()
        fallbacks = []
        seen = set()

        _gemma_label, gemma_provider = self._get_gemma_recovery_candidate()
        if gemma_provider:
            profile_name = self.config.get("smart_local_recovery", {}).get("profile", "gemma")
            profile = self._get_named_local_profile(profile_name) or {}
            provider_name = profile.get("provider", "ollama").lower()
            if provider_name != current:
                gemma_info = gemma_provider.get_info()
                fallbacks.append((provider_name, gemma_provider))
                seen.add((provider_name, gemma_info.get("model", "")))
        for name in self._fallback_order:
            if name == current:
                continue  # Skip the primary — it already failed
            try:
                p = self._create_provider(name)
                if p.is_available():
                    info = p.get_info()
                    key = (name, info.get("model", ""))
                    if key in seen:
                        continue
                    fallbacks.append((name, p))
                    seen.add(key)
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
                success, reply, latency, error = self._try_provider(
                    self.provider,
                    messages,
                    system_prompt,
                    max_tokens,
                    tag=self.provider.get_info()["name"],
                    allow_gemma_retry=True,
                )
                if success:
                    if not self._last_fallback_msg:
                        self._last_fallback_msg = ""
                    return reply, latency
                self._last_fallback_msg = ""
                primary_name = self.provider.get_info()["name"]
                errors.append(error)
                print(f"[BRAIN] Primary provider {primary_name} failed: {error}")
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

        gemma_already_tried = any("Gemma" in err or "gemma" in err for err in errors)
        for name, fallback in self._get_fallback_providers():
            if gemma_already_tried and name == "ollama" and self._is_gemma_model(fallback):
                continue
            try:
                print(f"[BRAIN] Falling back to {name}...")
                success, reply, latency, error = self._try_provider(
                    fallback,
                    messages,
                    system_prompt,
                    max_tokens,
                    tag=name,
                    allow_gemma_retry=not gemma_already_tried,
                )
                if not success:
                    errors.append(error)
                    print(f"[BRAIN] Fallback {name} failed: {error}")
                    gemma_already_tried = gemma_already_tried or ("gemma" in error.lower())
                    continue
                if self._last_fallback_msg and "Retried with" in self._last_fallback_msg:
                    print(f"[BRAIN] Fallback {name} succeeded via Gemma recovery in {latency}ms")
                    return reply, latency
                self._last_fallback_msg = (
                    f"(Served by {fallback.get_info()['name']} — "
                    f"primary provider failed or was unavailable)"
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
            "  - Anthropic: console.anthropic.com/settings/keys\n"
            "  - Local Gemma via Ollama: install Ollama, run `ollama pull gemma3:4b`, then use `/provider gemma`"
        )

    def switch_provider(self, provider_name: str) -> str:
        """Switch to a different AI provider at runtime."""
        provider_name = provider_name.lower().strip()
        local_profile = self._resolve_local_profile(provider_name)

        # Handle special commands
        if provider_name == "status":
            return self._provider_status()
        if provider_name == "fallback":
            self.fallback_enabled = not self.fallback_enabled
            self.config["auto_fallback"] = self.fallback_enabled
            status = "ON" if self.fallback_enabled else "OFF"
            return f"Auto-fallback: {status}"

        if local_profile:
            self._apply_local_profile(local_profile)
            provider_name = local_profile["provider"]
        elif provider_name not in PROVIDERS:
            available = ", ".join(PROVIDERS.keys())
            return (
                f"Unknown provider '{provider_name}'. Available: {available}\n"
                "Local shortcuts: gemma, gemma-fast, gemma:1b, gemma:4b, gemma:12b"
            )

        self.config["provider"] = provider_name
        self.provider = self._create_provider()

        if not self.provider.is_available():
            info = self.provider.get_info()
            if info.get("local"):
                if local_profile:
                    return self._local_provider_help(local_profile, info)
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
        if local_profile:
            return (
                f"Switched to {local_profile.get('label', info['name'])} via {info['name']} — "
                f"model: {info['model']}"
            )
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
        recovery_cfg = self.config.get("smart_local_recovery", {})
        if recovery_cfg.get("enabled", True):
            lines.append(f"Smart recovery: ON — unclear replies retry with {recovery_cfg.get('profile', 'gemma')}")
        lines.append(
            f"\nFree providers:\n"
            f"  Gemini  — aistudio.google.dev/apikey\n"
            f"  Groq    — console.groq.com/keys (fastest)"
        )
        lines.append(
            f"\nLocal Gemma shortcuts:\n"
            f"  /provider gemma      — Ollama gemma3:4b\n"
            f"  /provider gemma-fast — Ollama gemma3:1b\n"
            f"  /provider gemma:12b  — Ollama gemma3:12b\n"
            f"  Install first: ollama pull gemma3:4b"
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
        if not text or not text.strip():
            return  # Never add empty messages — APIs reject them
        self.history.append({"role": "user", "content": text.strip()})
        self._trim_history()

    def add_assistant_message(self, text: str):
        if not text or not text.strip():
            return
        self.history.append({"role": "assistant", "content": text.strip()})
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
                # Filter out any empty messages before sending
                clean_msgs = [m for m in self.history
                              if m.get("content") and m["content"].strip()]
                reply, latency = self._chat_with_fallback(
                    messages=clean_msgs,
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
