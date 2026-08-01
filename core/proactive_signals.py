"""
J.A.R.V.I.S — Proactive Signals  (opt-in, deterministic, content-free)

The backend of Ambient Assistance v1: surface a REAL local signal — repeated
on-screen errors, low battery — as a *suggestion*, so JARVIS can be helpful before
you ask. The rules are the whole point (an EV that guesses "you look stressed" is
the failure mode):

  · OFF BY DEFAULT. Every source needs its own explicit opt-in (a consent beyond
    the Persona proactivity switch). Nothing is watched until you say so.
  · DETERMINISTIC + ATTRIBUTABLE. A signal fires only on a real, countable event
    (N repeats, a battery %), and carries the reason. Never an emotion or health
    inference.
  · CONTENT-FREE. Screen-derived signals emit a COUNT and a summary only — never a
    screenshot, OCR text, or window title. The raw screen never leaves the box.
  · NO ACTIONS. This only reports. It never speaks, retries a tool, touches the
    desktop, or sends anything. The suggestion is a question you answer.

Sources are provider-injected (so it's testable with no real screen/battery), and
the Persona `proactivity` switch is the master gate: `off` ⇒ nothing surfaces.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

_STORE = Path.home() / ".jarvis" / "proactive.json"

# Known sources. `calendar` is reserved (no provider yet — future opt-in).
SOURCES = ("screen_errors", "battery", "calendar")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Consent:
    """Per-source opt-in, default OFF, stored locally. This IS the 'separate
    explicit user setting' each source requires."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else _STORE
        self.data: dict = {}
        self.load()

    def load(self) -> "Consent":
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.data = {}
        return self

    def save(self) -> "Consent":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        return self

    def enabled(self, source: str) -> bool:
        return bool(self.data.get(source, False))       # default OFF

    def set(self, source: str, on: bool) -> bool:
        if source not in SOURCES:
            return False
        self.data[source] = bool(on)
        return True

    def any_enabled(self) -> bool:
        return any(self.enabled(s) for s in SOURCES)

    def summary(self) -> dict:
        return {s: self.enabled(s) for s in SOURCES}


def _sig(source: str, dedup_key: str, severity: str, summary: str, suggestion: str) -> dict:
    # Stable id so a persistent incident dedups (same source+bucket ⇒ same id).
    sid = hashlib.sha1(f"{source}:{dedup_key}".encode("utf-8")).hexdigest()[:12]
    return {"id": sid, "source": source, "severity": severity,
            "observed_at": _now(), "summary": summary, "suggestion": suggestion}


# ── signal builders: raw (content-free) observation → contract signal ─────
# These are the ONLY place a signal is shaped, so privacy is enforced in one spot:
# they emit counts/percentages, never raw screen content.
def _screen_errors_signal(obs: dict) -> Optional[dict]:
    n = int(obs.get("count", 0) or 0)
    if n < 3:
        return None
    sev = "high" if n >= 8 else ("medium" if n >= 5 else "low")
    return _sig("screen_errors", f"sev:{sev}", sev,
                f"Errors repeated {n} times in the current approved screen session.",
                "Want me to inspect the error?")


def _battery_signal(obs: dict) -> Optional[dict]:
    percent = int(obs.get("percent", 100) or 100)
    if not obs.get("discharging", False) or percent >= 25:
        return None
    sev = "high" if percent < 10 else ("medium" if percent < 15 else "low")
    return _sig("battery", f"sev:{sev}", sev,
                f"Battery at {percent}% and discharging.",
                "Want me to note where you left off before it sleeps?")


_BUILDERS = {"screen_errors": _screen_errors_signal, "battery": _battery_signal}


def collect(consent: Consent, providers: dict, proactivity: str = "suggest_only") -> dict:
    """Gather signals from opted-in sources only. `providers` maps a source to a
    callable returning a content-free observation dict (or None). Pure — it never
    performs an action, and a source that isn't opted in is never even observed.

    Returns the contract: { enabled, proactivity, sources, signals:[…] }."""
    out = {"enabled": consent.any_enabled(), "proactivity": proactivity,
           "sources": consent.summary(), "signals": []}
    if proactivity == "off":            # master gate: Persona says stay silent
        out["enabled"] = False
        return out
    for source, provider in (providers or {}).items():
        if source not in _BUILDERS or not consent.enabled(source):
            continue                    # not opted in ⇒ not observed (no side effect)
        try:
            obs = provider()
        except Exception:
            obs = None
        if not obs:
            continue
        sig = _BUILDERS[source](obs)
        if sig:
            out["signals"].append(sig)
    return out
