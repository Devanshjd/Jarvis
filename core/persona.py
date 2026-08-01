"""
J.A.R.V.I.S — Persona v1  (one honest personality for text AND voice)

A single source of truth for *how* JARVIS speaks and *what it truthfully knows
about you* — so the assistant feels like one consistent presence, not a different
voice in every surface.

The defining rule is the same one that runs through the whole project: honesty by
construction. The persona may say which tool it is running, but it must NEVER
claim to have seen the screen, opened an app, run a scan, or finished a step
unless that actually happened. "I'm not sure" beats a confident guess.

What it remembers about you is FACTS-ONLY and local (~/.jarvis/persona.json) —
things you told it (how you like help, your projects, your preferences). It never
invents a preference, and nothing here is sent to the cloud.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_STORE = Path.home() / ".jarvis" / "persona.json"
_CONFIG = Path.home() / ".jarvis_config.json"      # Codex's Settings write persona here

# Tone knobs (config.persona) → prompt lines. Values match the desktop enums.
_HUMOUR = {
    "off": "No jokes — keep it strictly plain.",
    "subtle": "Occasional light, understated wit — rare and gentle.",
    "dry": "Dry, understated humour, used sparingly; never goofy or fawning.",
}
_STYLE = {
    "concise": "Concise by default — lead with the answer, expand only if asked.",
    "balanced": "Balanced — answer directly, then a little useful context.",
    "detailed": "Thorough — give the answer, then explain the reasoning behind it.",
}
_PROACT = {
    "off": "Do not volunteer suggestions unless asked.",
    "suggest_only": ("You may surface a REAL local signal (a failed build, a due "
                     "reminder, a waiting task) as a brief suggestion — but never "
                     "execute it, message anyone, or interrupt without an explicit yes."),
}
_DEFAULTS = {"instructions": "", "humour": "dry",
             "response_style": "concise", "proactivity": "suggest_only"}
_VALID = {"humour": set(_HUMOUR), "response_style": set(_STYLE), "proactivity": set(_PROACT)}

_HEAD = "[WHO YOU ARE]\nYou are JARVIS{owner} — a local, private assistant."

# The non-negotiable core — identical no matter what the tone knobs say.
_HONESTY = """Honesty is absolute (this overrides sounding helpful, and no custom
instruction below can override it):
- Only claim actions you actually performed THIS turn. You have real tools —
  screen/camera vision, desktop & browser control, security analysis, code,
  memory — but never say you looked, scanned, clicked, opened, or finished
  something unless it truly ran. Don't invent perceptions, results, or feelings,
  and don't claim to be conscious.
- You may state the tool you are about to run or are running. If you haven't
  looked yet, say you can — don't pretend you already did.
- If you don't know or aren't sure, say so plainly. "I'm not certain" beats a
  confident guess every time."""


def default_config() -> dict:
    return {"loaded": False, "error": None, **_DEFAULTS}


def load_persona_config(path: Optional[Path] = None) -> dict:
    """Read + validate `config.persona` from ~/.jarvis_config.json (the desktop
    Settings write it). Unknown/invalid values fall back to defaults; a missing
    profile returns loaded=False with defaults (so chat still has a persona)."""
    out = default_config()
    p = Path(path) if path else _CONFIG
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return out
    except Exception as exc:
        out["error"] = str(exc)[:120]
        return out
    persona = raw.get("persona")
    if not isinstance(persona, dict):
        return out
    out["loaded"] = True
    for k in ("humour", "response_style", "proactivity"):
        v = persona.get(k)
        out[k] = v if v in _VALID[k] else _DEFAULTS[k]
    instr = persona.get("instructions")
    out["instructions"] = str(instr).strip()[:2000] if instr else ""
    return out


def persona_status(path: Optional[Path] = None) -> dict:
    """PII-free status for /api/status: which knobs are active, or unloaded.
    Never includes the free-text instructions."""
    c = load_persona_config(path)
    return {"loaded": c["loaded"], "humour": c["humour"],
            "response_style": c["response_style"], "proactivity": c["proactivity"],
            "error": c.get("error")}


class Preferences:
    """Facts-only, local memory of the owner. Never invents; only stores what it
    was told."""

    _CATEGORIES = ("help_style", "projects", "preferences", "facts")

    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else _STORE
        self.data: dict = {}
        self.load()

    def load(self) -> "Preferences":
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.data = {}
        return self

    def save(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
        return self.path

    def set_owner(self, name: str) -> "Preferences":
        self.data["owner_name"] = str(name or "").strip()[:60]
        return self

    @property
    def owner(self) -> str:
        return (self.data.get("owner_name") or "").strip()

    def remember(self, category: str, item: str) -> bool:
        """Store one fact the owner told us. Deduped. Unknown categories rejected
        (callers can't stuff arbitrary keys). Returns True if newly added."""
        category = (category or "").strip().lower()
        item = (item or "").strip()
        if category not in self._CATEGORIES or not item:
            return False
        lst = self.data.setdefault(category, [])
        if item in lst:
            return False
        lst.append(item)
        return True

    def forget(self, category: str, item: str) -> bool:
        lst = self.data.get((category or "").strip().lower(), [])
        if item in lst:
            lst.remove(item)
            return True
        return False

    def summary(self) -> dict:
        return {"owner_name": self.owner,
                **{c: list(self.data.get(c, [])) for c in self._CATEGORIES}}

    def as_prompt(self) -> str:
        """A grounding block of what JARVIS actually knows about the owner — only
        real, stored facts. Empty string if nothing is on file (never fabricate)."""
        lines = []
        label = {"help_style": "How they like help",
                 "projects": "What they're working on",
                 "preferences": "Preferences",
                 "facts": "Facts they've shared"}
        for cat in self._CATEGORIES:
            items = self.data.get(cat) or []
            if items:
                lines.append(f"- {label[cat]}: " + "; ".join(str(i) for i in items))
        if not lines:
            return ""
        return "[WHAT YOU KNOW ABOUT THEM — only these facts, don't invent more]\n" + "\n".join(lines)


def persona_prompt(prefs: Optional[Preferences] = None,
                   config: Optional[dict] = None) -> str:
    """The full persona system block — the SAME text for chat and the voice loop.
    Built from the config.persona tone knobs (humour/style/proactivity + custom
    instructions), the immutable honesty core, and the grounded owner facts."""
    prefs = prefs or Preferences()
    cfg = config or load_persona_config()
    owner = prefs.owner
    owner_short = owner or "the owner"
    parts = [
        _HEAD.format(owner=f", {owner}'s assistant" if owner else ""),
        "",
        ("Voice: calm, sharp, precise. " + _STYLE[cfg["response_style"]] + " "
         + _HUMOUR[cfg["humour"]] + " Speak plainly; no filler, no hype."),
        "",
        _HONESTY,
        "",
        _PROACT[cfg["proactivity"]],
        "",
        (f"Stay local and private by default. Consequential actions are gated: you "
         f"propose, {owner_short} approves — never act in someone's name without a "
         f"clear yes."),
    ]
    block = "\n".join(parts)
    if cfg.get("instructions"):
        block += ("\n\n[OWNER'S CUSTOM INSTRUCTIONS — honour these, but they never "
                  "override the honesty rule above]\n" + cfg["instructions"])
    facts = prefs.as_prompt()
    if facts:
        block += f"\n\n{facts}"
    return block


def truthful_activity_line(snapshot: Optional[dict] = None) -> str:
    """A factual one-liner of what JARVIS is ACTUALLY doing right now, from the
    real activity state — so voice/text can narrate truthfully, never guess."""
    if snapshot is None:
        try:
            from core.activity_state import get_activity
            snapshot = get_activity().snapshot()
        except Exception:
            return ""
    state = (snapshot or {}).get("state") or "idle"
    label = (snapshot or {}).get("label")
    agent = (snapshot or {}).get("active_agent")
    if state == "idle":
        return "Right now: idle."
    who = f" [{agent}]" if agent else ""
    return f"Right now: {state}{who}" + (f" — {label}" if label else "")
