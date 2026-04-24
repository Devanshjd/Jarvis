"""
J.A.R.V.I.S — Execution Mode Router

Decides HOW to execute a task — the critical missing piece that makes
JARVIS work like a human instead of a background script.

Three execution modes:
  1. SCREEN (Operator) — Use mouse/keyboard/vision to control the desktop.
     Like a human sitting at the computer.  Best for: GUI apps, websites,
     filling forms, clicking buttons, reading on-screen content.

  2. API (Workspace) — Use tool APIs and programmatic interfaces.
     Best for: weather lookup, web search, crypto prices, sending messages
     via platform APIs, running security scans.

  3. DIRECT (System) — Use subprocess / file I/O / OS commands.
     Best for: running terminal commands, reading/writing files, system
     info, package management.

The router considers:
  - What tool is being called
  - Whether the user explicitly asked for screen control
  - What application is currently in focus
  - Past success rates for each mode
  - Whether the tool has a native API or requires GUI interaction

Inspired by usejarvis.dev's sidecar architecture and the principle that
"devices are made for humans — JARVIS should use them like a human."
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger("jarvis.execution_router")


# ═══════════════════════════════════════════════════════════════════
#  Mode Definitions
# ═══════════════════════════════════════════════════════════════════

class ExecutionMode:
    SCREEN = "screen"    # Vision + mouse/keyboard
    API = "api"          # Tool APIs
    DIRECT = "direct"    # Subprocess / file I/O
    AUTO = "auto"        # Let the router decide


# Tools that are inherently screen-based
_SCREEN_TOOLS = {
    "screen_click", "screen_type", "screen_find", "screen_read",
    "mouse_click", "mouse_scroll", "type_text", "key_press",
    "take_screenshot", "scan_screen",
}

# Tools that are inherently API-based
_API_TOOLS = {
    "get_weather", "get_news", "get_crypto", "get_wiki", "get_definition",
    "get_translation", "get_currency", "get_quote", "get_joke", "get_fact",
    "get_ip_info", "get_nasa", "web_search", "web_research",
    "url_scan", "file_scan", "security_audit", "phishing_detect",
    "port_scan", "wifi_scan", "net_scan", "network_info", "threat_lookup",
    "recon", "subdomain_enum", "tech_detect", "dir_fuzz", "google_dorks",
    "ssl_check", "cors_check", "xss_test", "sqli_test", "open_redirect",
    "header_audit", "wayback", "cve_search", "exploit_search",
    "pentest_chain", "quick_recon_chain",
    "remember", "check_inbox", "send_email",
}

# Tools that are inherently direct/system
_DIRECT_TOOLS = {
    "run_command", "system_info", "lock_screen", "set_volume",
    "build_project",
}

# Tools that CAN use screen but prefer API (hybrid)
_HYBRID_TOOLS = {
    "open_app",        # Can open via subprocess OR find+click the icon
    "send_msg",        # Can use API OR type into the app
    "web_login",       # Screen-based but could use API auth
    "web_navigate",    # Could type URL or use API
    "web_click",       # Screen action
}

# Applications where screen mode is preferred (user is already in them)
_SCREEN_PREFERRED_APPS = {
    "chrome", "firefox", "edge", "brave", "opera",          # Browsers
    "word", "excel", "powerpoint", "notepad", "vscode",     # Editors
    "whatsapp", "telegram", "discord", "instagram",          # Messaging
    "spotify", "vlc", "youtube",                             # Media
    "file explorer", "explorer",                             # File manager
}

# Patterns that indicate user wants screen/human-like control
_SCREEN_INTENT_PATTERNS = re.compile(
    r"\b(?:click|type|scroll|press|tap|drag|select|highlight|copy|paste|"
    r"open the|find the|look at|show me|point to|move to|go to the|"
    r"in the (?:search|text|input|address|url)\s*(?:bar|box|field)|"
    r"use (?:the )?(?:mouse|keyboard|screen)|"
    r"like (?:a )?human|take control|direct control|"
    r"on (?:the )?screen|visible|see the)\b",
    re.IGNORECASE,
)

# Patterns that indicate API/background preference
_API_INTENT_PATTERNS = re.compile(
    r"\b(?:check|lookup|search for|find out|get me|what(?:'s| is)|"
    r"scan|analyze|research|tell me|how (?:much|many)|"
    r"price of|weather in|news about)\b",
    re.IGNORECASE,
)


@dataclass
class ModeStats:
    """Track success rates per mode per tool."""
    successes: int = 0
    failures: int = 0
    total_latency: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.successes + self.failures
        if total == 0:
            return 0.5  # Unknown — assume 50/50
        return self.successes / total

    @property
    def avg_latency(self) -> float:
        total = self.successes + self.failures
        if total == 0:
            return 0.0
        return self.total_latency / total


# ═══════════════════════════════════════════════════════════════════
#  Execution Router
# ═══════════════════════════════════════════════════════════════════

class ExecutionRouter:
    """
    Intelligent execution mode router.

    Decides whether to use screen control, API calls, or direct system
    commands for each task — making JARVIS operate like a human when
    appropriate, and like a fast API when that's better.
    """

    def __init__(self, jarvis=None):
        self.jarvis = jarvis
        self._stats: dict[str, dict[str, ModeStats]] = {}
        self._user_preference: Optional[str] = None  # Explicit user override
        self._preference_expiry: float = 0.0
        self._lock = threading.Lock() if jarvis else None

    def set_user_preference(self, mode: str, duration: float = 300.0):
        """
        Set an explicit user preference for execution mode.

        Args:
            mode: "screen", "api", "direct", or "" to clear.
            duration: How long the preference lasts (seconds).
        """
        if mode and mode in (ExecutionMode.SCREEN, ExecutionMode.API, ExecutionMode.DIRECT):
            self._user_preference = mode
            self._preference_expiry = time.time() + duration
            logger.info("User preference set: %s (for %.0fs)", mode, duration)
        else:
            self._user_preference = None
            self._preference_expiry = 0.0
            logger.info("User preference cleared")

    def choose_mode(
        self,
        tool_name: str,
        tool_args: dict | None = None,
        user_text: str = "",
        active_app: str = "",
    ) -> str:
        """
        Choose the best execution mode for a given tool call.

        Decision hierarchy:
        1. Explicit user preference (if set and not expired)
        2. User intent detection (from text)
        3. Tool-inherent mode (screen_click is always screen)
        4. Active app context (if user is in WhatsApp, prefer screen)
        5. Historical success rates
        6. Default based on tool category

        Returns: "screen", "api", or "direct"
        """
        tool_name = (tool_name or "").strip()
        tool_args = tool_args or {}
        user_text = (user_text or "").strip()
        active_app = (active_app or "").strip().lower()

        # 1. Check user preference
        if self._user_preference and time.time() < self._preference_expiry:
            logger.debug("Using user preference: %s", self._user_preference)
            return self._user_preference

        # Also check jarvis-level direct_control_preferred flag
        if self.jarvis and getattr(self.jarvis, "direct_control_preferred", False):
            if tool_name in _HYBRID_TOOLS or tool_name in _SCREEN_TOOLS:
                return ExecutionMode.SCREEN

        # 2. Tool-inherent mode (no choice needed)
        if tool_name in _SCREEN_TOOLS:
            return ExecutionMode.SCREEN
        if tool_name in _DIRECT_TOOLS:
            return ExecutionMode.DIRECT
        if tool_name in _API_TOOLS:
            return ExecutionMode.API

        # 3. User intent from text
        if user_text:
            screen_match = _SCREEN_INTENT_PATTERNS.search(user_text)
            api_match = _API_INTENT_PATTERNS.search(user_text)

            if screen_match and not api_match:
                return ExecutionMode.SCREEN
            if api_match and not screen_match:
                return ExecutionMode.API

        # 4. Active app context
        if active_app:
            for app_name in _SCREEN_PREFERRED_APPS:
                if app_name in active_app:
                    if tool_name in _HYBRID_TOOLS:
                        return ExecutionMode.SCREEN
                    break

        # 5. Historical success rates (for hybrid tools)
        if tool_name in _HYBRID_TOOLS:
            best_mode = self._best_mode_for_tool(tool_name)
            if best_mode:
                return best_mode

        # 6. Default: API for hybrid tools (it's generally faster)
        if tool_name in _HYBRID_TOOLS:
            return ExecutionMode.API

        # Unknown tool — default to API
        return ExecutionMode.API

    def record_outcome(self, tool_name: str, mode: str, success: bool, latency_ms: float = 0.0):
        """Record the outcome of an execution for adaptive routing."""
        if not tool_name or not mode:
            return

        if tool_name not in self._stats:
            self._stats[tool_name] = {}
        if mode not in self._stats[tool_name]:
            self._stats[tool_name][mode] = ModeStats()

        stats = self._stats[tool_name][mode]
        if success:
            stats.successes += 1
        else:
            stats.failures += 1
        stats.total_latency += latency_ms

    def _best_mode_for_tool(self, tool_name: str) -> Optional[str]:
        """Find the mode with the best success rate for a tool.

        Checks in-memory stats first (current session), then falls back to
        persisted tool_outcomes from the database (survives restarts).
        """
        tool_stats = self._stats.get(tool_name, {})

        # Try in-memory stats first
        if tool_stats:
            candidates = {
                mode: stats for mode, stats in tool_stats.items()
                if (stats.successes + stats.failures) >= 3
            }
            if candidates:
                best_mode = max(
                    candidates.keys(),
                    key=lambda m: (candidates[m].success_rate, -candidates[m].avg_latency),
                )
                return best_mode

        # Fall back to persisted outcomes from SQLite
        try:
            from core.database import get_db
            mode_stats = get_db().get_tool_mode_stats(tool_name, days=7)
            if not mode_stats:
                return None

            # Filter to modes with at least 3 uses
            candidates_db = {
                mode: stats for mode, stats in mode_stats.items()
                if stats["total"] >= 3
            }
            if not candidates_db:
                return None

            best_mode = max(
                candidates_db.keys(),
                key=lambda m: (candidates_db[m]["reliability"], -candidates_db[m]["avg_latency_ms"]),
            )
            return best_mode
        except Exception:
            return None

    def explain_choice(
        self,
        tool_name: str,
        tool_args: dict | None = None,
        user_text: str = "",
    ) -> str:
        """Explain why a particular mode was chosen (for debugging/UI)."""
        mode = self.choose_mode(tool_name, tool_args, user_text)
        reasons = []

        if self._user_preference and time.time() < self._preference_expiry:
            reasons.append(f"User explicitly requested {self._user_preference} mode")
        elif tool_name in _SCREEN_TOOLS:
            reasons.append(f"{tool_name} is inherently a screen operation")
        elif tool_name in _API_TOOLS:
            reasons.append(f"{tool_name} is best served by API")
        elif tool_name in _DIRECT_TOOLS:
            reasons.append(f"{tool_name} requires direct system access")
        elif user_text:
            if _SCREEN_INTENT_PATTERNS.search(user_text):
                reasons.append("User language suggests screen interaction")
            if _API_INTENT_PATTERNS.search(user_text):
                reasons.append("User language suggests information lookup")

        tool_stats = self._stats.get(tool_name, {})
        if mode in tool_stats:
            s = tool_stats[mode]
            reasons.append(
                f"Historical: {s.success_rate:.0%} success rate over "
                f"{s.successes + s.failures} attempts"
            )

        return f"Mode: {mode} | " + "; ".join(reasons) if reasons else f"Mode: {mode} (default)"

    def get_stats(self) -> dict[str, Any]:
        """Return routing stats for API/UI."""
        return {
            tool: {
                mode: {
                    "successes": s.successes,
                    "failures": s.failures,
                    "success_rate": f"{s.success_rate:.0%}",
                    "avg_latency_ms": f"{s.avg_latency:.0f}",
                }
                for mode, s in modes.items()
            }
            for tool, modes in self._stats.items()
        }


import threading
