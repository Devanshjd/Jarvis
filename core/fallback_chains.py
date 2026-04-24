"""
J.A.R.V.I.S -- Fallback Chain Definitions

When a tool fails, JARVIS tries the next method in its fallback chain
before giving up.  Each chain entry specifies a mode and description
that the executor can use to retry intelligently.

Example:  open_app fails via subprocess → try Win key + type + Enter
          → try finding the taskbar icon and clicking it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class FallbackStep:
    """One fallback method for a tool."""
    mode: str               # "direct", "screen", "clipboard", "api"
    description: str        # human-readable description
    tool_override: str = "" # if set, use this tool instead of the original
    extra_args: dict = None # extra args to merge

    def __post_init__(self):
        if self.extra_args is None:
            self.extra_args = {}


# ═══════════════════════════════════════════════════════════════════
#  Fallback chains — keyed by canonical tool name
# ═══════════════════════════════════════════════════════════════════

FALLBACK_CHAINS: dict[str, list[FallbackStep]] = {

    "open_app": [
        FallbackStep(
            mode="direct",
            description="Launch via subprocess / os.startfile",
        ),
        FallbackStep(
            mode="screen",
            description="Win key → type app name → Enter",
        ),
        FallbackStep(
            mode="screen",
            description="Find taskbar icon and click it",
            tool_override="screen_click",
        ),
    ],

    "type_text": [
        FallbackStep(
            mode="direct",
            description="pyautogui.typewrite (ASCII path)",
        ),
        FallbackStep(
            mode="clipboard",
            description="Copy to clipboard → Ctrl+V paste",
        ),
    ],

    "send_msg": [
        FallbackStep(
            mode="api",
            description="Plugin API call (messaging plugin)",
        ),
        FallbackStep(
            mode="screen",
            description="Open app → find contact → type message → send",
        ),
    ],

    "screen_click": [
        FallbackStep(
            mode="screen",
            description="AI vision locate + click",
        ),
        FallbackStep(
            mode="screen",
            description="Retry with different screenshot crop",
        ),
        FallbackStep(
            mode="direct",
            description="Tab to element + Enter",
            tool_override="key_press",
            extra_args={"key": "tab"},
        ),
    ],

    "web_search": [
        FallbackStep(
            mode="direct",
            description="Open URL in browser via webbrowser.open",
        ),
        FallbackStep(
            mode="screen",
            description="Open Chrome → type in address bar → Enter",
        ),
    ],

    "run_command": [
        FallbackStep(
            mode="direct",
            description="subprocess.run with shell=True",
        ),
        FallbackStep(
            mode="screen",
            description="Win+R → type command → Enter",
        ),
    ],

    "screen_type": [
        FallbackStep(
            mode="screen",
            description="Vision-locate field → click → type",
        ),
        FallbackStep(
            mode="direct",
            description="Tab to field → type_text",
            tool_override="type_text",
        ),
        FallbackStep(
            mode="clipboard",
            description="Click field → clipboard paste",
        ),
    ],

    "lock_screen": [
        FallbackStep(
            mode="direct",
            description="ctypes.windll.user32.LockWorkStation()",
        ),
        FallbackStep(
            mode="direct",
            description="Win+L shortcut",
            tool_override="key_combo",
            extra_args={"keys": "win+l"},
        ),
    ],

    "set_volume": [
        FallbackStep(
            mode="direct",
            description="nircmd.exe or PowerShell volume control",
        ),
        FallbackStep(
            mode="screen",
            description="Click system tray volume → drag slider",
        ),
    ],
}


def get_fallback_chain(tool_name: str) -> list[FallbackStep]:
    """Get fallback chain for a tool. Returns empty list if none defined."""
    return FALLBACK_CHAINS.get(tool_name, [])


def get_next_fallback(
    tool_name: str,
    failed_attempt: int,
) -> Optional[FallbackStep]:
    """Get the next fallback step after N failures.

    Args:
        tool_name: canonical tool name
        failed_attempt: 0-based index of last failed attempt

    Returns:
        Next FallbackStep, or None if all fallbacks exhausted.
    """
    chain = get_fallback_chain(tool_name)
    next_idx = failed_attempt + 1  # skip the method that just failed
    if next_idx < len(chain):
        return chain[next_idx]
    return None
