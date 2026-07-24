"""
J.A.R.V.I.S — Owner Greeting & Face Gate

Turns the raw Face ID recognizer into two owner-aware behaviours:

  1. GREETING  — when JARVIS sees its enrolled owner, craft a personalised,
     time-of-day-aware line ("Good evening, Dev.") — but only once per
     cooldown window, so it never spams the same greeting every frame.

  2. FACE GATE — a hard check the rest of the system can call before a
     sensitive action: "is the person in front of the camera *right now*
     the authorised owner?" Returns a clear authorised / denied verdict.
     This is the security angle for the military path — "only Dev can
     authorize this."

100% local. Sits on top of core.face_id (OpenCV LBPH). No cloud.

Usage:
    from core.owner_greeting import get_greeter
    g = get_greeter()
    line = g.greet_from_webcam()          # -> "Good evening, Dev." or None
    ok   = g.verify_owner_webcam()        # -> (True, "Dev", 0.81)
"""
from __future__ import annotations

import logging
import time
from typing import Optional

logger = logging.getLogger("jarvis.greeting")

# Don't re-greet the same person more often than this (seconds).
GREET_COOLDOWN_S = 600  # 10 minutes

# A face gate for sensitive actions must clear a HIGHER bar than a friendly
# greeting — a wrong "yes that's Dev" here could authorise something it
# shouldn't. LBPH confidence is normalised 0-1 (higher = better match).
GATE_MIN_CONFIDENCE = 0.55
GREET_MIN_CONFIDENCE = 0.40


class OwnerGreeter:
    """Owner-aware greeting + face-gate on top of FaceID."""

    def __init__(self):
        # name -> last unix time we greeted them
        self._last_greeted: dict[str, float] = {}

    # ─── Greeting ─────────────────────────────────────────────────────────

    def _time_of_day(self) -> str:
        h = time.localtime().tm_hour
        if h < 12:
            return "Good morning"
        if h < 17:
            return "Good afternoon"
        if h < 22:
            return "Good evening"
        return "Working late"

    def compose_greeting(self, name: str, first_time_today: bool = True) -> str:
        """Craft the spoken line for a recognised owner."""
        tod = self._time_of_day()
        if tod == "Working late":
            return f"Working late, {name}? I'm here. Systems are online."
        if first_time_today:
            return f"{tod}, {name}. Welcome back. All systems online."
        return f"{tod}, {name}."

    def _should_greet(self, name: str) -> bool:
        last = self._last_greeted.get(name, 0.0)
        return (time.time() - last) >= GREET_COOLDOWN_S

    def greet_from_frame(self, jpeg_bytes: bytes) -> Optional[dict]:
        """Recognise a face in a frame; if it's the owner and the cooldown
        has elapsed, return a greeting dict. Otherwise None.

        Returns: {"name", "confidence", "text"} or None.
        """
        from core.face_id import get_faceid
        name, conf = get_faceid().recognize_frame(jpeg_bytes)
        return self._maybe_greet(name, conf)

    def greet_from_webcam(self) -> Optional[dict]:
        """Same as greet_from_frame but grabs one webcam frame itself."""
        from core.face_id import get_faceid
        name, conf = get_faceid().recognize_webcam()
        return self._maybe_greet(name, conf)

    def _maybe_greet(self, name: Optional[str], conf: float) -> Optional[dict]:
        if not name or conf < GREET_MIN_CONFIDENCE:
            return None
        if not self._should_greet(name):
            return None  # seen recently — stay quiet
        first_time_today = self._is_first_today(name)
        self._last_greeted[name] = time.time()
        text = self.compose_greeting(name, first_time_today)
        logger.info("Greeting owner %r (conf %.2f): %s", name, conf, text)
        return {"name": name, "confidence": conf, "text": text}

    def _is_first_today(self, name: str) -> bool:
        last = self._last_greeted.get(name)
        if not last:
            return True
        return time.localtime(last).tm_yday != time.localtime().tm_yday

    # ─── Face gate (for sensitive actions) ────────────────────────────────

    def verify_owner_frame(self, jpeg_bytes: bytes,
                           owner: Optional[str] = None) -> tuple[bool, Optional[str], float]:
        """Hard check: is this frame the authorised owner?

        If `owner` is given, the recognised name must match it. Requires a
        HIGHER confidence than a greeting. Returns (authorised, name, conf).
        """
        from core.face_id import get_faceid
        name, conf = get_faceid().recognize_frame(jpeg_bytes)
        return self._decide_gate(name, conf, owner)

    def verify_owner_webcam(self, owner: Optional[str] = None
                            ) -> tuple[bool, Optional[str], float]:
        from core.face_id import get_faceid
        name, conf = get_faceid().recognize_webcam()
        return self._decide_gate(name, conf, owner)

    def _decide_gate(self, name: Optional[str], conf: float,
                     owner: Optional[str]) -> tuple[bool, Optional[str], float]:
        if not name or conf < GATE_MIN_CONFIDENCE:
            return False, name, conf
        if owner is not None and name.lower() != owner.lower():
            return False, name, conf
        return True, name, conf


# Module-level singleton
_greeter: Optional[OwnerGreeter] = None


def get_greeter() -> OwnerGreeter:
    global _greeter
    if _greeter is None:
        _greeter = OwnerGreeter()
    return _greeter
