"""
J.A.R.V.I.S — Activity State  (honest, real-time state for the orb UI)

A single, thread-safe source of truth for "what is JARVIS doing right now",
exposed in /api/status as `activity` so the desktop orb can reflect the TRUTH
(idle / thinking / tool_running / speaking / error) and the active crew member.

Contract (stable — the orb depends on it):
    activity = {
      "state":        "idle | listening | thinking | tool_running | speaking | error",
      "active_agent": "JARVIS | ULTRON | FRIDAY | VISION | EDITH" | null,
      "label":        "Running Bandit security scan"            | null,
      "tool":         "security_scan"                           | null,
      "run_id":       "<8-hex>"                                 | null,
      "since":        "<ISO-8601 UTC>",
      "error":        "<message>"                               | null,
    }

Honesty rules baked in:
  · Transitions come from REAL lifecycle events only (the runtime's _core_mode,
    the tool executor, the crew dispatch) — never an LLM's guess about itself.
  · `listening` and backend `speaking` are set from the actual mic/TTS
    lifecycle. Renderer-owned mic states (e.g. the Gemini voice loop) are set
    by the renderer; see PLAN.md.
  · Every entry point is wrapped try/finally by its caller so a crash returns to
    `idle` or `error`, never a stuck spinner.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

VALID_STATES = {"idle", "listening", "thinking", "tool_running", "speaking", "error"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class _Activity:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = "idle"
        self.active_agent: str | None = None
        self.label: str | None = None
        self.tool: str | None = None
        self.run_id: str | None = None
        self.error: str | None = None
        self.since = _now()

    def _set(self, state: str, *, agent: str | None = None, label: str | None = None,
             tool: str | None = None, error: str | None = None,
             new_run: bool = False) -> None:
        if state not in VALID_STATES:
            return
        with self._lock:
            self.state = state
            self.active_agent = agent
            self.label = label
            self.tool = tool
            self.error = error
            if new_run or self.run_id is None:
                self.run_id = uuid.uuid4().hex[:8]
            self.since = _now()

    # ── transitions (called from real lifecycle points) ──────────────────
    def idle(self) -> None:
        with self._lock:
            self.state = "idle"
            self.active_agent = self.label = self.tool = self.error = None
            self.run_id = None
            self.since = _now()

    def thinking(self, agent: str = "JARVIS", label: str = "Thinking") -> None:
        self._set("thinking", agent=agent, label=label, new_run=True)

    def tool_running(self, tool: str, agent: str = "JARVIS",
                     label: str | None = None) -> None:
        self._set("tool_running", agent=agent, tool=tool,
                  label=label or f"Running {tool}")

    def agent_working(self, agent: str, label: str, tool: str | None = None) -> None:
        """A named specialist is doing real work (e.g. ULTRON running Bandit)."""
        self._set("tool_running", agent=agent, label=label, tool=tool)

    def listening(self) -> None:
        self._set("listening", agent="JARVIS", label="Listening", new_run=True)

    def speaking(self, label: str = "Speaking") -> None:
        self._set("speaking", agent="JARVIS", label=label)

    def error(self, message: str) -> None:
        self._set("error", error=str(message)[:200], label="Something went wrong")

    def from_core_mode(self, mode: str) -> None:
        """Bridge the runtime's existing _core_mode state machine (which already
        fires at real lifecycle points) into this contract. Unknown modes are
        ignored so specialist states (set directly) aren't clobbered."""
        m = (mode or "").lower()
        if m == "thinking":
            # Don't downgrade a specific specialist/tool state back to generic.
            with self._lock:
                if self.state in ("tool_running",):
                    return
            self.thinking()
        elif m == "speaking":
            self.speaking()
        elif m in ("idle", "ready", "listening_done"):
            self.idle()
        elif m in ("alert", "error"):
            self.error("runtime alert")
        elif m == "listening":
            self.listening()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "state": self.state,
                "active_agent": self.active_agent,
                "label": self.label,
                "tool": self.tool,
                "run_id": self.run_id,
                "since": self.since,
                "error": self.error,
            }


_activity = _Activity()


def get_activity() -> _Activity:
    return _activity
