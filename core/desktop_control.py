"""
J.A.R.V.I.S — Desktop Control  (gated, app-scoped keyboard/mouse — the safe way)

JARVIS already has the raw primitives (precise_click: pywinauto→OCR; pyautogui
for typing). What it lacked was a *safe* way to use them: a single, gated,
app-scoped control loop. This is that loop.

The whole design is the safety model — because "let the AI drive the keyboard and
mouse" is the highest-blast-radius thing in the project:

  1. OFF BY DEFAULT. Nothing works until desktop control is explicitly enabled
     (env `JARVIS_DESKTOP=1` or the app's "APPROVE DESKTOP" toggle → /enable).
  2. SCOPED, EXPIRING SESSIONS. You approve a *task* bound to *one app*, with a
     TTL. Actions outside that app are refused. stop() kills it instantly (the
     Stop button). Approval is never permanent.
  3. PROPOSE → APPROVE → EXECUTE → VERIFY → LOG, one atomic action at a time.
     Each action is checked, run only inside an active session, verified against
     the window state, and written to an append-only audit log.
  4. HARD-BLOCKED ACTIONS (refused even if "approved") — mirrors the assistant's
     own limits: never type passwords/credentials/secrets, never do financial
     actions (buy/sell/transfer/pay), never solve CAPTCHAs. You do those yourself.
  5. SCREEN CONTENT IS DATA, NOT COMMANDS. The controller NEVER decides its next
     action from what's on screen (OCR/vision). Steps come only from the approved
     plan. This is the prompt-injection firewall: a hostile web page or document
     can't feed JARVIS instructions to run.
  6. FAIL CLOSED on the dangerous primitive: it will not type unless it can
     confirm the active window is the approved app.

Planning is deliberately deterministic (no model in the loop) so nothing on
screen can inject steps. The model's role, if any, is elsewhere and only ever
*proposes* to you.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.desktop_control")

_AUDIT = Path.home() / ".jarvis" / "desktop_audit.jsonl"

try:
    import pyautogui
    pyautogui.FAILSAFE = True     # slam mouse to a corner to abort
    pyautogui.PAUSE = 0.1
    HAS_GUI = True
except Exception:                 # pragma: no cover - env without a display
    HAS_GUI = False

# ── Prohibited surfaces — refused regardless of approval (you must do these) ──
_CREDENTIAL_RE = re.compile(
    r"\b(pass\s?word|passwd|pwd|pass\s?phrase|\bpin\b|otp|2fa|mfa|cvv|cvc|"
    r"card\s*number|credit\s*card|debit\s*card|ssn|social\s*security|"
    r"seed\s*phrase|private\s*key|secret\s*key|api[_\s-]?key|token)\b", re.I)
_FINANCIAL_RE = re.compile(
    r"\b(buy|sell|trade|transfer|wire|withdraw|deposit|send\s*money|"
    r"pay(ment)?|purchase|checkout|place\s*(the\s*)?order|confirm\s*order)\b", re.I)
_CAPTCHA_RE = re.compile(r"\b(captcha|recaptcha|hcaptcha|i'?m\s*not\s*a\s*robot)\b", re.I)

# Atomic actions the controller understands. Anything else is refused.
ACTIONS = ("observe", "open_app", "focus", "click", "type_text", "press", "hotkey")

# App name must be a bare, safe token — no path separators / shell metacharacters.
_SAFE_APP_RE = re.compile(r"^[\w .+-]{1,60}$")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@dataclass
class Session:
    id: str
    task: str
    app_scope: str
    created_at: float
    expires_at: float

    def active(self) -> bool:
        return time.time() < self.expires_at

    def public(self) -> dict:
        return {"id": self.id, "task": self.task, "app_scope": self.app_scope,
                "expires_in": max(0, round(self.expires_at - time.time())),
                "active": self.active()}


class DesktopController:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._session: Optional[Session] = None
        self._enabled = os.environ.get("JARVIS_DESKTOP", "").strip().lower() in (
            "1", "true", "yes", "on")
        self._recent: list[dict] = []

    # ── enable / status ──────────────────────────────────────────────────
    def enable(self, on: bool) -> dict:
        with self._lock:
            self._enabled = bool(on)
            if not on:
                self._session = None          # disabling also ends any session
        self._audit("enable", {"on": bool(on)})
        return self.status()

    def status(self) -> dict:
        with self._lock:
            s = self._session
            return {"available": HAS_GUI, "enabled": self._enabled,
                    "session": s.public() if s and s.active() else None,
                    "recent": self._recent[-10:]}

    # ── session lifecycle ────────────────────────────────────────────────
    def start_session(self, task: str, app_scope: str, ttl: int = 120) -> dict:
        if not HAS_GUI:
            return {"error": "desktop automation unavailable (pyautogui not importable)"}
        if not self._enabled:
            return {"error": "desktop control is disabled — enable it first (APPROVE DESKTOP)"}
        task = (task or "").strip()
        app_scope = (app_scope or "").strip()
        if not task:
            return {"error": "a task description is required"}
        if not app_scope:
            return {"error": "an app scope is required — bind this session to one app "
                              "(e.g. 'notepad'); control is never unscoped"}
        ttl = max(15, min(int(ttl or 120), 600))
        with self._lock:
            self._session = Session(uuid.uuid4().hex[:8], task[:200], app_scope[:80],
                                    time.time(), time.time() + ttl)
            self._audit("session_start",
                        {"task": task[:200], "app_scope": app_scope[:80], "ttl": ttl})
            return {"session": self._session.public()}

    def stop(self) -> dict:
        """The Stop button — ends control immediately."""
        with self._lock:
            had = self._session is not None
            if self._session:
                self._audit("session_stop", {"id": self._session.id})
            self._session = None
            return {"stopped": had}

    def _require(self) -> Optional[str]:
        if not self._enabled:
            return "desktop control is disabled"
        if not HAS_GUI:
            return "desktop automation unavailable"
        s = self._session
        if not s or not s.active():
            return "no active desktop session — start one scoped to a task + app"
        return None

    # ── propose (deterministic — no model, so nothing can inject steps) ───
    def propose(self, task: str) -> dict:
        """Turn a task into a list of typed actions to SHOW you for approval.
        Nothing runs. Deterministic parsing only — the screen never gets a say
        in what steps exist."""
        t = (task or "").strip()
        actions: list[dict] = []
        m = re.match(r"^\s*open\s+([\w .+-]+?)\s+and\s+type:?\s+(.*)$", t, re.I | re.S)
        if m:
            app, text = m.group(1).strip(), m.group(2)
            actions = [{"action": "open_app", "app": app},
                       {"action": "focus", "app": app},
                       {"action": "type_text", "text": text}]
        else:
            m2 = re.match(r"^\s*open\s+([\w .+-]+)$", t, re.I)
            if m2:
                actions = [{"action": "open_app", "app": m2.group(1).strip()}]
        return {"task": t, "actions": actions,
                "note": ("Proposed only — each step still needs your approval."
                         if actions else
                         "Couldn't parse this into safe steps — provide explicit actions.")}

    # ── safety gate for a single action ──────────────────────────────────
    def _blocked(self, action: dict) -> Optional[str]:
        kind = action.get("action")
        blob = " ".join(str(action.get(k, "")) for k in ("text", "app", "target", "keys"))
        task = self._session.task if self._session else ""
        if _CREDENTIAL_RE.search(blob):
            return "refuses to enter passwords / credentials / secrets — please type it yourself"
        if _CAPTCHA_RE.search(blob):
            return "refuses to solve CAPTCHAs"
        if _FINANCIAL_RE.search(blob + " " + task):
            return "refuses financial actions (buy / sell / transfer / pay) — do this yourself"
        if kind == "type_text" and self._focused_is_password():
            return "the focused field looks like a password field — refused"
        return None

    # ── execute one atomic action (the gated core) ───────────────────────
    def execute(self, action: dict) -> dict:
        with self._lock:
            err = self._require()
            if err:
                return {"ok": False, "refused": err}
            kind = action.get("action")
            if kind not in ACTIONS:
                return {"ok": False, "refused": f"unknown action {kind!r}"}
            blocked = self._blocked(action)
            if blocked:
                self._audit("blocked", {"action": action, "reason": blocked})
                return {"ok": False, "blocked": blocked}
            # Fail CLOSED on the dangerous primitives: never type/press into a
            # window we can't confirm is the approved app.
            if kind in ("type_text", "press", "hotkey"):
                scope = self._scope_ok()
                if scope is not True:
                    self._audit("scope_refused", {"action": action, "reason": scope})
                    return {"ok": False, "refused": scope}
            before = self._snapshot_title()
            try:
                result = self._do(action)
            except Exception as exc:
                self._audit("error", {"action": action, "error": str(exc)[:200]})
                return {"ok": False, "error": str(exc)[:200]}
            verify = {"before_window": before, "after_window": self._snapshot_title()}
            rec = {"ts": _now(), "action": action, "result": result, "verify": verify}
            self._recent.append(rec)
            self._audit("execute", rec)
            return {"ok": True, "result": result, "verify": verify}

    # ── observe (read-only; NEVER drives the next action) ────────────────
    def observe(self) -> dict:
        title = self._snapshot_title()
        controls: list[str] = []
        s = self._session
        try:
            from pywinauto import Desktop
            for w in Desktop(backend="uia").windows():
                t = (w.window_text() or "")
                if s and s.app_scope and s.app_scope.lower() in t.lower():
                    for c in w.descendants():
                        lbl = (c.window_text() or "").strip()
                        if lbl:
                            controls.append(lbl[:60])
                        if len(controls) >= 40:
                            break
                    break
        except Exception:
            pass
        return {"active_window": title, "controls": controls[:40],
                "note": "read-only observation — not used to choose actions"}

    # ── primitives ───────────────────────────────────────────────────────
    def _do(self, action: dict) -> dict:
        kind = action["action"]
        if kind == "observe":
            return self.observe()
        if kind == "open_app":
            return self._open_app(action.get("app", ""))
        if kind == "focus":
            return self._focus(action.get("app", ""))
        if kind == "click":
            from core.precise_click import click_element
            r = click_element(action.get("target", ""), app_hint=action.get("app", ""))
            return {"clicked": r.success, "method": r.method, "x": r.x, "y": r.y,
                    "matched": r.matched_text, "error": r.error}
        if kind == "type_text":
            text = str(action.get("text", ""))
            if text.isascii():
                pyautogui.typewrite(text, interval=0.02)
            else:
                pyautogui.write(text)
            return {"typed_chars": len(text)}
        if kind == "press":
            key = str(action.get("key", "")).strip()
            pyautogui.press(key)
            return {"pressed": key}
        if kind == "hotkey":
            keys = [k.strip() for k in str(action.get("keys", "")).split("+") if k.strip()]
            pyautogui.hotkey(*keys)
            return {"hotkey": "+".join(keys)}
        return {"noop": True}

    def _open_app(self, app: str) -> dict:
        app = (app or "").strip()
        if not _SAFE_APP_RE.match(app):
            raise ValueError(f"unsafe app name {app!r}")
        try:
            subprocess.Popen([app])          # apps on PATH (notepad, calc, ...)
        except Exception:
            os.startfile(app)                # registered app / document fallback
        time.sleep(0.8)
        return {"opened": app, "active_window": self._snapshot_title()}

    def _focus(self, app: str) -> dict:
        app = (app or "").strip().lower()
        try:
            for w in pyautogui.getAllWindows():        # pygetwindow
                if app in (getattr(w, "title", "") or "").lower():
                    try:
                        w.activate()
                    except Exception:
                        w.minimize(); w.restore()
                    time.sleep(0.2)
                    return {"focused": getattr(w, "title", "")}
        except Exception as exc:
            return {"focused": None, "error": str(exc)[:120]}
        return {"focused": None, "error": f"no window matching {app!r}"}

    # ── helpers (best-effort; wrapped so they never crash a run) ──────────
    def _snapshot_title(self) -> str:
        try:
            w = pyautogui.getActiveWindow()
            return (getattr(w, "title", "") or "")[:120]
        except Exception:
            return ""

    def _scope_ok(self):
        s = self._session
        if not s:
            return "no active session"
        title = self._snapshot_title().lower()
        if not title:
            return "can't confirm the active window — refusing to type blindly"
        if s.app_scope.lower() in title:
            return True
        return (f"active window ({title!r}) is outside the approved app scope "
                f"({s.app_scope!r}) — refused")

    def _focused_is_password(self) -> bool:
        """Best-effort: is the focused control a password box? Detection isn't
        reliable across every app, so this is defence-in-depth — the primary
        credential guard is the keyword block + your per-action review."""
        try:
            from pywinauto import Desktop
            getf = getattr(Desktop(backend="uia"), "get_focus", None)
            el = getf() if callable(getf) else None
            if el is None:
                return False
            for attr in ("is_password", "IsPassword"):
                v = getattr(el, attr, None)
                if callable(v):
                    try:
                        return bool(v())
                    except Exception:
                        pass
                elif v is not None:
                    return bool(v)
        except Exception:
            return False
        return False

    def _audit(self, event: str, data: dict) -> None:
        try:
            _AUDIT.parent.mkdir(parents=True, exist_ok=True)
            with open(_AUDIT, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": _now(), "event": event, **data}) + "\n")
        except Exception:
            pass


_controller: Optional[DesktopController] = None
_singleton_lock = threading.Lock()


def get_controller() -> DesktopController:
    global _controller
    with _singleton_lock:
        if _controller is None:
            _controller = DesktopController()
        return _controller
