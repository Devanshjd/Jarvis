"""
J.A.R.V.I.S — Mode Auto-Switcher
Context-aware automatic mode selection.

Movie JARVIS adapts its behavior to what's happening.
When Tony is coding, JARVIS talks code.
When there's a threat, JARVIS goes defensive.

This engine auto-switches modes based on:
- What the user is doing (active window)
- What they're talking about (intent)
- Time of day
- Explicit requests ("enter cyber mode")
"""

import re
import logging
from typing import Optional

logger = logging.getLogger("jarvis.modes")


# Mode definitions with auto-switch triggers
MODE_CONFIG = {
    "General": {
        "label": "GEN",
        "triggers": [],  # Default fallback
        "auto_switch": False,
    },
    "Code/Dev": {
        "label": "DEV",
        "triggers": ["coding", "terminal"],  # Window categories
        "intent_triggers": ["code"],           # Intent categories
        "auto_switch": True,
    },
    "Research": {
        "label": "RES",
        "triggers": [],
        "intent_triggers": ["search"],
        "auto_switch": False,  # Only on explicit request
    },
    "Projects": {
        "label": "PRJ",
        "triggers": [],
        "intent_triggers": [],
        "auto_switch": False,
    },
    "Analysis": {
        "label": "ANA",
        "triggers": ["spreadsheet"],
        "intent_triggers": [],
        "auto_switch": True,
    },
    "Screen": {
        "label": "SCR",
        "triggers": [],
        "intent_triggers": ["screen"],
        "auto_switch": True,
    },
    "File Edit": {
        "label": "FIL",
        "triggers": [],
        "intent_triggers": ["files"],
        "auto_switch": True,
    },
    "Advisor": {
        "label": "ADV",
        "triggers": [],
        "intent_triggers": ["personal"],
        "auto_switch": False,
    },
    "Cyber": {
        "label": "SEC",
        "triggers": ["security"],
        "intent_triggers": ["security"],
        "auto_switch": True,
    },
}

# Natural language mode switch patterns
MODE_SWITCH_PATTERNS = {
    "General": re.compile(
        r"\b(normal\s+mode|general\s+mode|default\s+mode|regular\s+mode|assistant\s+mode)\b", re.I
    ),
    "Code/Dev": re.compile(
        r"\b(dev(eloper)?\s+mode|code\s+mode|coding\s+mode|programming\s+mode|"
        r"help\s+me\s+(code|program|develop))\b", re.I
    ),
    "Research": re.compile(
        r"\b(research\s+mode|analyst?\s+mode|investigate)\b", re.I
    ),
    "Cyber": re.compile(
        r"\b(cyber\s+mode|security\s+mode|guardian\s+mode|defense\s+mode|"
        r"threat\s+mode|protect\s+mode|sec\s+mode)\b", re.I
    ),
    "Advisor": re.compile(
        r"\b(advisor?\s+mode|personal\s+mode|life\s+mode|coach\s+mode|"
        r"i\s+need\s+advice)\b", re.I
    ),
    "Screen": re.compile(
        r"\b(screen\s+mode|visual\s+mode|look\s+at\s+(my\s+)?screen)\b", re.I
    ),
}

# Explicit enter/exit patterns
ENTER_MODE = re.compile(
    r"(?:enter|switch\s+to|go\s+to|activate|enable|use)\s+(\w+(?:\s+\w+)?)\s*(?:mode)?", re.I
)
EXIT_MODE = re.compile(
    r"(?:exit|leave|deactivate|disable|stop)\s+(\w+(?:\s+\w+)?)\s*(?:mode)?|"
    r"(?:exit|leave|back\s+to)\s+(?:this\s+)?mode", re.I
)


class ModeAutoSwitcher:
    """
    Automatically switches JARVIS modes based on context.

    Rules:
    1. Explicit requests ALWAYS override auto-switch
    2. Auto-switch is gentle — only triggers on clear signals
    3. If user manually set a mode, don't auto-switch for 5 min
    4. Announce mode changes so user isn't confused
    """

    def __init__(self, app):
        self.app = app
        self.current_mode = "General"
        self._manual_override = False
        self._manual_override_time = 0
        self._manual_cooldown = 300  # 5 min after manual switch
        self._last_auto_mode = "General"

    def check_explicit_switch(self, text: str) -> Optional[str]:
        """
        Check if user is explicitly requesting a mode switch.
        Returns mode name or None.
        """
        # Check "enter X mode" patterns
        for mode_name, pattern in MODE_SWITCH_PATTERNS.items():
            if pattern.search(text):
                return mode_name

        # Check generic "enter/switch to" pattern
        match = ENTER_MODE.search(text)
        if match:
            requested = match.group(1).strip().lower()
            # Fuzzy match mode names
            for mode_name in MODE_CONFIG:
                if requested in mode_name.lower() or mode_name.lower().startswith(requested):
                    return mode_name

        # Check exit mode
        if EXIT_MODE.search(text):
            return "General"

        return None

    def suggest_mode(self, intent=None, window_category: str = None) -> Optional[str]:
        """
        Suggest a mode based on context.
        Returns mode name or None if no change needed.
        """
        # Respect manual override cooldown
        if self._manual_override:
            import time
            if (time.time() - self._manual_override_time) < self._manual_cooldown:
                return None
            self._manual_override = False

        # Check intent-based triggers
        if intent and hasattr(intent, 'category'):
            for mode_name, config in MODE_CONFIG.items():
                if not config.get("auto_switch"):
                    continue
                intent_triggers = config.get("intent_triggers", [])
                if intent.category in intent_triggers and mode_name != self.current_mode:
                    return mode_name

        # Check window-based triggers
        if window_category:
            for mode_name, config in MODE_CONFIG.items():
                if not config.get("auto_switch"):
                    continue
                if window_category in config.get("triggers", []) and mode_name != self.current_mode:
                    return mode_name

        return None

    def switch(self, mode: str, manual: bool = False) -> str:
        """
        Execute a mode switch.
        Returns announcement message.
        """
        import time

        if mode not in MODE_CONFIG:
            return f"Unknown mode: {mode}"

        old_mode = self.current_mode
        self.current_mode = mode

        if manual:
            self._manual_override = True
            self._manual_override_time = time.time()

        # Update brain mode
        if hasattr(self.app, 'brain'):
            self.app.brain.set_mode(mode)

        # Update UI
        if hasattr(self.app, 'mode_label'):
            label = MODE_CONFIG[mode]["label"]
            self.app.root.after(0, lambda: self.app.mode_label.config(text=label))

        if manual:
            return f"{mode} mode active."
        else:
            return f"Switching to {mode} mode."

    def get_mode_label(self, mode: str = None) -> str:
        mode = mode or self.current_mode
        return MODE_CONFIG.get(mode, {}).get("label", "GEN")
