"""
J.A.R.V.I.S — Cross-device Handoff  ("continue this on my phone")

The laptop and the phone already talk to the SAME backend, so they already share
one conversation + memory — they're one JARVIS, not two chats. Handoff is the
small nudge on top: "continue this over there" drops a marker the other device
picks up, so the conversation visibly follows you instead of you hunting for it.

Deliberately tiny + safe: a handoff is a NOTE + a short context summary, never an
action. It moves no data anywhere new (the history is already shared), controls
nothing, and auto-clears once the receiving device acknowledges it. One pending
handoff at a time, persisted locally so a gap between devices doesn't lose it.
"""
from __future__ import annotations

import json
import secrets
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_STORE = Path.home() / ".jarvis" / "handoff.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class HandoffStore:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else _STORE
        self._lock = threading.RLock()

    def _load(self) -> Optional[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _save(self, h: Optional[dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(h or {}, indent=2), encoding="utf-8")

    def start(self, to: str, from_device: str = "laptop",
              summary: str = "", note: str = "") -> dict:
        """Mark a handoff to the target device ('phone' or 'laptop')."""
        to = "phone" if to == "phone" else "laptop"
        h = {"id": secrets.token_hex(4), "to": to,
             "from": "phone" if from_device == "phone" else "laptop",
             "created_at": _now(), "summary": (summary or "")[:400],
             "note": (note or "")[:200], "acked": False}
        with self._lock:
            self._save(h)
        return h

    def latest(self, for_device: Optional[str] = None) -> Optional[dict]:
        """The pending (un-acked) handoff, optionally only if it targets
        `for_device`. Returns None when there's nothing to pick up."""
        with self._lock:
            h = self._load()
        if not h or not h.get("id") or h.get("acked"):
            return None
        if for_device and h.get("to") != for_device:
            return None
        return h

    def ack(self, handoff_id: str) -> bool:
        """The receiving device confirms it picked the handoff up (stops the nudge)."""
        with self._lock:
            h = self._load()
            if h and h.get("id") == handoff_id and not h.get("acked"):
                h["acked"] = True
                self._save(h)
                return True
        return False


_store: Optional[HandoffStore] = None
_lock = threading.Lock()


def get_handoff() -> HandoffStore:
    global _store
    with _lock:
        if _store is None:
            _store = HandoffStore()
        return _store
