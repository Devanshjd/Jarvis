"""
J.A.R.V.I.S — Proactive Voice Routing  (safe, narrow voice control of consent)

Lets you flip an ambient-signal source by voice — "turn on battery suggestions",
"disable screen-error alerts" — WITHOUT the danger of a misheard word silently
enabling monitoring of your machine. Two rules make it safe:

  1. DETERMINISTIC + NARROW. A plain regex, not the LLM, decides if an utterance
     is a consent command. Anything ambiguous ("what's my battery?", "turn on the
     lights") matches nothing and falls through to normal chat.
  2. NEVER SILENTLY ENABLE. A matched command only PROPOSES — it echoes the exact
     source and new state and waits. The consent flips only after an explicit
     spoken "yes". "no" cancels; anything else drops the pending change.

The apply path is the SAME `Consent` store the settings toggle and the token-gated
endpoint use — one source of truth for what's watched.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Optional

_ON = re.compile(r"\b(turn on|enable|start|allow|activate|switch on)\b", re.I)
_OFF = re.compile(r"\b(turn off|disable|stop|switch off|deactivate|mute)\b", re.I)
_SOURCES = [
    ("battery", re.compile(r"\bbattery\b", re.I)),
    ("screen_errors", re.compile(r"\bscreen[\s-]?errors?\b", re.I)),
]
_YES = re.compile(r"\b(yes|yeah|yep|confirm|do it|go ahead|sure|affirmative|please do)\b", re.I)
_NO = re.compile(r"\b(no|nope|cancel|never ?mind|don'?t|do not|leave it)\b", re.I)

_LABEL = {"battery": "battery", "screen_errors": "screen-error"}


def parse_consent_command(text: str) -> Optional[dict]:
    """Deterministic: return {source, state} for a clear on/off command over a
    known source, else None. Ambiguous (no source, or neither/both verbs) → None,
    so it can never act on a guess."""
    t = text or ""
    on, off = bool(_ON.search(t)), bool(_OFF.search(t))
    if on == off:                       # neither, or contradictory → not a command
        return None
    for name, rx in _SOURCES:
        if rx.search(t):
            return {"source": name, "state": on}
    return None                          # a verb but no known source → not a command


def is_affirmation(text: str) -> bool:
    return bool(_YES.search(text or ""))


def is_negation(text: str) -> bool:
    return bool(_NO.search(text or ""))


class _Pending:
    """The single consent change awaiting a spoken confirmation (short TTL)."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._src: Optional[str] = None
        self._state: Optional[bool] = None
        self._at = 0.0

    def set(self, source: str, state: bool) -> None:
        with self._lock:
            self._src, self._state, self._at = source, state, time.time()

    def get(self, ttl: float = 30.0):
        with self._lock:
            if self._src is None or (time.time() - self._at) > ttl:
                return None
            return (self._src, self._state)

    def clear(self) -> None:
        with self._lock:
            self._src = self._state = None


_pending = _Pending()


def route_utterance(text: str, consent) -> dict:
    """The safe router. Returns {handled, ...}:
      · a fresh command → {handled, kind:"confirm", source, state, reply}  (NO write)
      · a "yes" to a pending change → {handled, kind:"applied", ...}       (writes)
      · a "no" → {handled, kind:"cancelled", reply}
      · anything else → {handled: False}  (let normal chat take it)
    `consent` is a core.proactive_signals.Consent."""
    text = (text or "").strip()

    pend = _pending.get()
    if pend:
        src, state = pend
        if is_affirmation(text):
            consent.set(src, state)
            consent.save()
            _pending.clear()
            return {"handled": True, "kind": "applied", "source": src, "state": state,
                    "reply": f"{_LABEL[src]} suggestions are {'on' if state else 'off'}."}
        if is_negation(text):
            _pending.clear()
            return {"handled": True, "kind": "cancelled",
                    "reply": "Okay — I left it as it was."}
        _pending.clear()                 # not a yes/no → the change lapses (safe)

    cmd = parse_consent_command(text)
    if cmd:
        _pending.set(cmd["source"], cmd["state"])
        return {"handled": True, "kind": "confirm",
                "source": cmd["source"], "state": cmd["state"],
                "reply": (f"Turn {'on' if cmd['state'] else 'off'} "
                          f"{_LABEL[cmd['source']]} suggestions — say yes to confirm.")}

    return {"handled": False}
