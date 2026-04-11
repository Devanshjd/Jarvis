"""
J.A.R.V.I.S - Runtime Capability Registry
Live view of what JARVIS can do right now, how it should do it,
and how reliable each ability currently is.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Optional


SCHEMA_ALIASES = {
    "scan_screen": "screen_scan",
}


ABILITY_HINTS = {
    "get_news": {
        "category": "research",
        "execution_mode": "research",
        "verification": "Fetch current headlines and return concise topic-aware results, not an unrelated tool prompt.",
        "aliases": ["news", "headlines", "latest news", "current news"],
        "plugin": "web_intel",
    },
    "get_weather": {
        "category": "research",
        "execution_mode": "research",
        "verification": "Return weather details for the requested city or the default location.",
        "aliases": ["weather", "forecast", "temperature", "rain"],
        "plugin": "web_intel",
    },
    "get_crypto": {
        "category": "research",
        "execution_mode": "research",
        "verification": "Return the requested crypto price or market detail clearly.",
        "aliases": ["crypto", "bitcoin", "ethereum", "btc", "eth", "price"],
        "plugin": "web_intel",
    },
    "send_msg": {
        "category": "communication",
        "execution_mode": "operator",
        "verification": "Verify the correct chat is open, the message box has focus, and the send action actually happened.",
        "aliases": ["text", "message", "dm", "whatsapp", "telegram", "instagram", "discord", "tell someone"],
        "plugin": "messaging",
        "ask_for_missing": ["contact", "platform", "message"],
    },
    "open_app": {
        "category": "desktop",
        "execution_mode": "direct",
        "verification": "Verify the target app window becomes active before moving to the next step.",
        "aliases": ["open", "launch", "start", "run app"],
    },
    "screen_find": {
        "category": "screen",
        "execution_mode": "vision",
        "verification": "Return whether the UI element was found with usable coordinates or a clear miss.",
        "aliases": ["find on screen", "locate element", "search bar", "button"],
        "component": "screen_interact",
    },
    "screen_click": {
        "category": "screen",
        "execution_mode": "vision",
        "verification": "Verify focus or UI state changed after the click.",
        "aliases": ["click button", "click on screen", "press button"],
        "component": "screen_interact",
    },
    "screen_type": {
        "category": "screen",
        "execution_mode": "vision",
        "verification": "Verify text appeared in the intended field, not somewhere else.",
        "aliases": ["type into field", "enter text in box"],
        "component": "screen_interact",
    },
    "screen_read": {
        "category": "screen",
        "execution_mode": "vision",
        "verification": "Read visible UI text and summarize only what is relevant.",
        "aliases": ["read screen", "what is on screen"],
        "component": "screen_interact",
    },
    "scan_screen": {
        "category": "screen",
        "execution_mode": "vision",
        "verification": "Capture the screen and answer the requested question about it.",
        "aliases": ["scan screen", "see my screen", "look at screen"],
    },
    "mouse_click": {
        "category": "input",
        "execution_mode": "direct",
        "verification": "Only report success if permission was granted and the click completed.",
        "aliases": ["mouse click", "click coordinates"],
    },
    "type_text": {
        "category": "input",
        "execution_mode": "direct",
        "verification": "Use only when the correct field is already focused.",
        "aliases": ["type text", "keyboard type"],
    },
    "key_press": {
        "category": "input",
        "execution_mode": "direct",
        "verification": "Use precise key names and verify the UI changed as expected.",
        "aliases": ["press key", "hit enter", "press escape"],
    },
    "web_research": {
        "category": "research",
        "execution_mode": "research",
        "verification": "Return a concise synthesis with sources or evidence.",
        "aliases": ["research", "investigate", "look into"],
        "component": "researcher",
    },
    "research_cve": {
        "category": "research",
        "execution_mode": "research",
        "verification": "Return the CVE details and severity clearly.",
        "aliases": ["cve research", "security advisory"],
        "component": "researcher",
    },
    "build_project": {
        "category": "development",
        "execution_mode": "agent",
        "verification": "Create or modify project files, then report what was built and what still needs testing.",
        "aliases": ["build website", "make app", "create tool", "generate project"],
        "component": "dev_agent",
    },
    "set_reminder": {
        "category": "productivity",
        "execution_mode": "direct",
        "verification": "Store the reminder and surface the due time clearly.",
        "aliases": ["remind me", "set reminder"],
    },
    "set_timer": {
        "category": "productivity",
        "execution_mode": "direct",
        "verification": "Store the countdown duration and confirm it back.",
        "aliases": ["timer", "countdown"],
    },
    "send_email": {
        "category": "communication",
        "execution_mode": "direct",
        "verification": "Verify recipient, subject, and sending outcome before claiming success.",
        "aliases": ["email", "mail"],
        "plugin": "email",
    },
    "check_inbox": {
        "category": "communication",
        "execution_mode": "direct",
        "verification": "Return inbox status or a concise unread summary.",
        "aliases": ["inbox", "emails", "mail"],
        "plugin": "email",
    },
    "url_scan": {
        "category": "security",
        "execution_mode": "analysis",
        "verification": "Return concrete findings rather than generic warnings.",
        "aliases": ["scan url", "check link", "phishing"],
        "plugin": "cyber",
    },
    "recon": {
        "category": "security",
        "execution_mode": "analysis",
        "verification": "Run reconnaissance and summarize discovered targets and risks.",
        "aliases": ["recon", "enumeration", "subdomains"],
        "plugin": "pentest",
    },
}


@dataclass
class Capability:
    name: str
    description: str
    category: str = "general"
    required_args: list[str] = field(default_factory=list)
    execution_mode: str = "direct"
    verification: str = ""
    aliases: list[str] = field(default_factory=list)
    available: bool = True
    reliability: float = 0.5
    plugin: str = ""
    component: str = ""
    learned_hint: str = ""

    def to_prompt_line(self) -> str:
        status = "available" if self.available else "unavailable"
        rel = f"{self.reliability:.2f}"
        required = ", ".join(self.required_args) if self.required_args else "none"
        verify = self.verification or "verify the result before claiming success"
        return (
            f"- {self.name} [{status}; reliability={rel}; category={self.category}; mode={self.execution_mode}] "
            f"needs={required}. {self.description}"
            + (f" Learned: {self.learned_hint}." if self.learned_hint else "")
            + f" Verification: {verify}"
        )

    def to_user_line(self) -> str:
        status = "" if self.available else " (currently unavailable)"
        rel = int(round(self.reliability * 100))
        learned = f" Learned: {self.learned_hint}." if self.learned_hint else ""
        return f"- {self.name}: {self.description}{learned}{status} [{self.category}, {rel}% reliability]"


@dataclass(frozen=True)
class CapabilityMatch:
    capability: Capability
    score: float
    reason: str = ""


class CapabilityRegistry:
    """Runtime registry of JARVIS abilities."""

    def __init__(self, jarvis):
        self.jarvis = jarvis

    def refresh(self) -> list[Capability]:
        return self.list_capabilities()

    def list_capabilities(self, available_only: bool = False) -> list[Capability]:
        executor = getattr(getattr(self.jarvis, "orchestrator", None), "executor", None)
        tool_names = list(getattr(executor, "available_tools", []))
        capabilities = [self._build_capability(name) for name in tool_names]
        capabilities.sort(key=lambda item: (not item.available, item.category, item.name))
        if available_only:
            capabilities = [cap for cap in capabilities if cap.available]
        return capabilities

    def get_capability(self, name: str) -> Optional[Capability]:
        executor = getattr(getattr(self.jarvis, "orchestrator", None), "executor", None)
        if not executor or name not in getattr(executor, "available_tools", []):
            return None
        return self._build_capability(name)

    def describe_for_user(self, limit: int = 18) -> str:
        capabilities = self.list_capabilities(available_only=True)
        if not capabilities:
            return "I do not have a live capability registry yet."
        lines = ["JARVIS runtime abilities:"]
        for cap in capabilities[:limit]:
            lines.append(cap.to_user_line())
        if len(capabilities) > limit:
            lines.append(f"- ...and {len(capabilities) - limit} more abilities are loaded.")
        return "\n".join(lines)

    def get_prompt_context(self, user_text: str = "", limit: int = 8) -> str:
        capabilities = self.list_capabilities(available_only=True)
        if not capabilities:
            return ""

        lines = ["[RUNTIME CAPABILITIES]"]
        for cap in capabilities[:limit]:
            lines.append(cap.to_prompt_line())

        if user_text:
            relevant = self.find_relevant_capabilities(user_text, limit=5)
            if relevant:
                lines.append("[MOST RELEVANT CAPABILITIES FOR THIS REQUEST]")
                for cap in relevant:
                    lines.append(cap.to_prompt_line())

        lines.append(
            "[ABILITY SELECTION RULES]\n"
            "- Prefer a real capability when the user wants an action, not a generic chat reply.\n"
            "- Ask only for missing required arguments.\n"
            "- For app navigation, prefer screen-aware or operator-style abilities over blind key sequences when possible.\n"
            "- Never claim a task succeeded until the expected UI or tool outcome is verified."
        )
        return "\n".join(lines)

    def resolve_request(self, user_text: str, min_score: float = 4.5) -> Optional[CapabilityMatch]:
        """
        Resolve a user request to the most likely live capability.

        This mirrors the explicit execution-registry idea from operator-first
        systems: prefer a concrete action surface when the request clearly maps
        to one loaded ability, instead of hoping downstream chat logic chooses it.
        """
        text_lower = (user_text or "").lower().strip()
        if not text_lower:
            return None

        query_tokens = self._tokenize(text_lower)
        if not query_tokens:
            return None

        ranked: list[tuple[float, Capability]] = []
        for capability in self.list_capabilities(available_only=True):
            score = self._score_capability(capability, query_tokens, text_lower)
            score += self._intent_bonus(capability, text_lower)
            if score > 0:
                ranked.append((score, capability))

        if not ranked:
            return None

        ranked.sort(key=lambda item: item[0], reverse=True)
        best_score, best_capability = ranked[0]
        second_score = ranked[1][0] if len(ranked) > 1 else 0.0

        if best_score < min_score:
            return None
        if second_score and best_score < second_score + 1.0 and best_score < (min_score + 1.5):
            return None

        return CapabilityMatch(
            capability=best_capability,
            score=best_score,
            reason=self._intent_reason(best_capability, text_lower),
        )

    def find_relevant_capabilities(self, user_text: str, limit: int = 5) -> list[Capability]:
        query_tokens = self._tokenize(user_text)
        if not query_tokens:
            return []

        ranked: list[tuple[float, Capability]] = []
        for cap in self.list_capabilities(available_only=True):
            score = self._score_capability(cap, query_tokens, user_text.lower())
            if score > 0:
                ranked.append((score, cap))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [cap for _, cap in ranked[:limit]]

    def _build_capability(self, tool_name: str) -> Capability:
        schema = self._get_schema(tool_name)
        hint = ABILITY_HINTS.get(tool_name, {})
        description = ""
        required = []
        if schema:
            description = schema.get("description", "")
            required = list(schema.get("input_schema", {}).get("required", []))

        if not description:
            description = self._fallback_description(tool_name)

        task_brain = getattr(self.jarvis, "task_brain", None)
        learned_hint = ""
        if task_brain and hasattr(task_brain, "get_capability_hint"):
            try:
                learned_hint = task_brain.get_capability_hint(tool_name)
            except Exception:
                learned_hint = ""

        return Capability(
            name=tool_name,
            description=description,
            category=hint.get("category", self._infer_category(tool_name)),
            required_args=required,
            execution_mode=hint.get("execution_mode", "direct"),
            verification=hint.get("verification", ""),
            aliases=list(hint.get("aliases", [])),
            available=self._is_available(tool_name, hint),
            reliability=self._get_reliability(tool_name),
            plugin=hint.get("plugin", ""),
            component=hint.get("component", ""),
            learned_hint=learned_hint,
        )

    def _get_schema(self, tool_name: str) -> Optional[dict]:
        try:
            from core.tool_schemas import get_schema_for_tool
        except Exception:
            return None

        schema = get_schema_for_tool(tool_name)
        if schema:
            return schema

        alias = SCHEMA_ALIASES.get(tool_name)
        if alias:
            return get_schema_for_tool(alias)
        return None

    def _get_reliability(self, tool_name: str) -> float:
        intelligence = getattr(self.jarvis, "intelligence", None)
        feedback = getattr(intelligence, "feedback", None)
        if feedback and hasattr(feedback, "get_tool_reliability"):
            try:
                return float(feedback.get_tool_reliability(tool_name))
            except Exception:
                return 0.5
        return 0.5

    def _is_available(self, tool_name: str, hint: dict) -> bool:
        executor = getattr(getattr(self.jarvis, "orchestrator", None), "executor", None)
        if not executor or tool_name not in getattr(executor, "available_tools", []):
            return False

        plugin_name = hint.get("plugin")
        if plugin_name:
            manager = getattr(self.jarvis, "plugin_manager", None)
            plugins = getattr(manager, "plugins", {}) if manager else {}
            if plugin_name not in plugins:
                return False

        component_name = hint.get("component")
        if component_name and not getattr(self.jarvis, component_name, None):
            return False

        return True

    def _score_capability(self, capability: Capability, query_tokens: set[str], text_lower: str) -> float:
        haystack = " ".join(
            [capability.name, capability.description, " ".join(capability.aliases), capability.category]
        ).lower()
        haystack_tokens = self._tokenize(haystack)
        overlap = len(query_tokens & haystack_tokens)
        score = float(overlap)

        if capability.name in text_lower:
            score += 3.0

        for alias in capability.aliases:
            alias_lower = alias.lower()
            if alias_lower in text_lower:
                score += 2.0

        if capability.execution_mode == "operator" and any(word in text_lower for word in ("send", "text", "message", "call")):
            score += 1.5
        if capability.category == "screen" and any(word in text_lower for word in ("screen", "button", "click", "field", "box")):
            score += 1.5
        if capability.category == "development" and any(word in text_lower for word in ("build", "create", "website", "app", "bot", "agent")):
            score += 1.5

        return score

    def _intent_bonus(self, capability: Capability, text_lower: str) -> float:
        bonus = 0.0

        if capability.name == "send_msg":
            blocked_tell_context = re.search(
                r"\b(?:news|headlines|weather|forecast|temperature|crypto|bitcoin|btc|eth|"
                r"wikipedia|wiki|define|meaning|translate|time|date)\b",
                text_lower,
            )
            send_like = re.search(r"\b(?:send|text|texting|message|messaging|msg|dm)\b", text_lower)
            tell_like = re.search(
                r"\btell\s+\w+\s+(?:that\s+|i'?m\s+|i\s+am\s+|to\s+|on\s+(?:whatsapp|telegram|instagram|discord))",
                text_lower,
            )
            if send_like or (tell_like and not blocked_tell_context):
                bonus += 4.0
            if re.search(r"\b(?:whatsapp|telegram|instagram|discord)\b", text_lower):
                bonus += 2.0
            if re.search(r"\b(?:that|say|saying|i'?m|i\s+am|i'?ll|i\s+will)\b", text_lower):
                bonus += 1.5
            if re.search(r"\b(?:open|launch|start|run)\s+(?:the\s+)?(?:app\s+)?(?:whatsapp|telegram|instagram|discord)\b", text_lower):
                bonus += 1.5

        elif capability.name == "open_app":
            if re.search(r"\b(?:open|launch|start|run)\b", text_lower):
                bonus += 4.0

        elif capability.name == "web_search":
            if re.search(r"\b(?:search|google|look\s*up|find|websearch|web\s+search)\b", text_lower):
                bonus += 4.0

        elif capability.name == "get_news":
            if re.search(r"\b(?:news|headlines)\b", text_lower):
                bonus += 5.0

        elif capability.name == "get_weather":
            if re.search(r"\b(?:weather|forecast|temperature|rain)\b", text_lower):
                bonus += 5.0

        elif capability.name == "get_crypto":
            if re.search(r"\b(?:crypto|bitcoin|btc|eth|ethereum)\b", text_lower):
                bonus += 5.0

        elif capability.name == "security_audit":
            if re.search(r"\b(?:system\s+safe|safe\s+or\s+not|security\s+check|security\s+audit|scan\s+my\s+system)\b", text_lower):
                bonus += 5.0

        elif capability.name == "web_login":
            if re.search(r"\b(?:log\s*in|login|sign\s*in)\b", text_lower):
                bonus += 5.0

        elif capability.name == "build_project":
            if re.search(r"\b(?:build|create|make|generate)\b", text_lower):
                bonus += 3.0
            if re.search(r"\b(?:website|app|application|program|tool|script|game|bot|agent|project)\b", text_lower):
                bonus += 2.0

        elif capability.name.startswith("screen_"):
            if re.search(r"\b(?:screen|button|field|box|input|menu|element|ui)\b", text_lower):
                bonus += 3.0

        elif capability.name.startswith(("mouse_", "key_", "type_")):
            if re.search(r"\b(?:mouse|keyboard|type|press|shortcut|key)\b", text_lower):
                bonus += 3.0

        if capability.execution_mode in {"operator", "vision", "direct"} and re.search(
            r"\b(?:mouse|keyboard|screen|desktop|computer)\b", text_lower
        ):
            bonus += 1.0

        return bonus

    def _intent_reason(self, capability: Capability, text_lower: str) -> str:
        if capability.name == "send_msg":
            return "matched messaging intent and platform/contact cues"
        if capability.name == "get_news":
            return "matched current news/headlines phrasing"
        if capability.name == "get_weather":
            return "matched weather/forecast phrasing"
        if capability.name == "get_crypto":
            return "matched crypto price phrasing"
        if capability.name == "open_app":
            return "matched app-launch phrasing"
        if capability.name == "web_search":
            return "matched search phrasing"
        if capability.name == "security_audit":
            return "matched system safety/security phrasing"
        if capability.name == "web_login":
            return "matched login phrasing"
        if capability.name.startswith("screen_"):
            return "matched screen/UI interaction phrasing"
        if capability.name.startswith(("mouse_", "key_", "type_")):
            return "matched direct input-control phrasing"
        if capability.name == "build_project":
            return "matched build/create project phrasing"
        return f"matched {capability.category} capability cues"

    def _infer_category(self, tool_name: str) -> str:
        if tool_name.startswith(("screen_", "scan_screen")):
            return "screen"
        if tool_name.startswith(("mouse_", "key_", "type_")):
            return "input"
        if tool_name.startswith(("research", "web_")):
            return "research"
        if tool_name.startswith(("url_", "port_", "wifi_", "net_", "phishing_", "security_", "recon", "xss_", "sqli_")):
            return "security"
        if tool_name.startswith(("send_", "check_inbox")):
            return "communication"
        if tool_name.startswith(("set_timer", "set_reminder")):
            return "productivity"
        if tool_name.startswith(("build_", "run_python", "save_file", "git_", "pip_")):
            return "development"
        return "general"

    def _fallback_description(self, tool_name: str) -> str:
        return "Use the " + tool_name.replace("_", " ") + " ability when the task clearly matches it."

    def _tokenize(self, text: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9_+-]+", text.lower()) if len(token) > 1}
