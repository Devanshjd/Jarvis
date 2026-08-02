"""
J.A.R.V.I.S — Device Registry  (paired phones: pairing, scoped tokens, revocation)

The auth core for reaching the laptop brain from a phone (over Tailscale). The
network layer (Tailscale Serve, tailnet-only) is one gate; THIS is the second,
independent, app-layer gate:

  · PAIRING is desktop-initiated. The desktop mints a 6-digit code (5-min TTL);
    the phone submits it once to receive its OWN token. A phone can't self-pair.
  · Per-device tokens are stored HASHED (sha256); the raw token is shown to the
    phone exactly once. Each device is revocable independently.
  · SCOPE: a phone token reaches a small allowlist — chat, status, voice — and is
    denied everything high-blast-radius (desktop control, terminal, self-modify,
    device management). A lost phone can talk to JARVIS; it can't drive the PC.

All OFF unless `JARVIS_REMOTE=1`. FastAPI still binds 127.0.0.1 only — remote
reach is Tailscale Serve's job, not a wider bind.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_STORE = Path.home() / ".jarvis" / "devices.json"
_PAIR_TTL = 300.0            # a pairing code is valid for 5 minutes
# Brute-force defence for the 6-digit code (a million possibilities):
_MAX_CODE_FAILS = 5         # a code is BURNED after this many wrong guesses (any source)
_MAX_SOURCE_FAILS = 8       # a source is locked out after this many failures…
_SOURCE_WINDOW = 60.0       # …within this many seconds (generic per-source cooldown)

# The ONLY endpoint prefixes a paired phone may reach (default-deny allowlist).
# Deliberately excludes desktop/terminal/self-modify/edith/agent/files/jobs/
# persona/device-management and even proactive consent — chat, status, voice only.
_PHONE_ALLOW = ("/api/chat", "/api/history", "/api/status", "/api/token/health",
                "/api/voice/", "/api/tts/", "/api/stt/", "/api/proactive/status",
                "/api/handoff")     # continue-here: pick up + ack a handoff


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def remote_enabled() -> bool:
    return os.environ.get("JARVIS_REMOTE", "").strip().lower() in ("1", "true", "yes", "on")


def _hash(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def device_scope_allows(device: Optional[dict], path: str) -> bool:
    """A phone-scoped device may reach only the allowlist; anything else is denied."""
    if (device or {}).get("scope") != "phone":
        return False
    return any(path.startswith(p) for p in _PHONE_ALLOW)


class DeviceRegistry:
    def __init__(self, path: Optional[Path] = None) -> None:
        self.path = Path(path) if path else _STORE
        self._lock = threading.RLock()
        self._pending: Optional[dict] = None         # {code, expiry, fails}
        self._src_fails: dict = {}                   # source → [failure timestamps]

    # ── persistence ──────────────────────────────────────────────────────
    def _load(self) -> dict:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
            return d if isinstance(d, dict) and "devices" in d else {"devices": []}
        except Exception:
            return {"devices": []}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    # ── pairing (desktop starts, phone completes once) ───────────────────
    def start_pairing(self) -> dict:
        code = f"{secrets.randbelow(1_000_000):06d}"
        expiry = time.time() + _PAIR_TTL
        with self._lock:
            self._pending = {"code": code, "expiry": expiry, "fails": 0}
        return {"code": code,
                "expires_at": datetime.fromtimestamp(expiry, timezone.utc).isoformat(),
                "ttl_seconds": int(_PAIR_TTL)}

    # ── brute-force throttle ─────────────────────────────────────────────
    def _throttled(self, source: str) -> bool:
        now = time.time()
        hits = [t for t in self._src_fails.get(source, []) if now - t < _SOURCE_WINDOW]
        self._src_fails[source] = hits
        return len(hits) >= _MAX_SOURCE_FAILS

    def _note_fail(self, source: str) -> None:
        self._src_fails.setdefault(source, []).append(time.time())

    def complete_pairing(self, code: str, device_name: str = "phone",
                         source: str = "local") -> Optional[dict]:
        with self._lock:
            # Per-source cooldown: too many recent failures from this caller → stop.
            if self._throttled(source):
                return None
            pend = self._pending
            if not pend or time.time() > pend["expiry"]:
                self._note_fail(source)
                return None                          # no code / expired
            if not secrets.compare_digest(str(code or ""), pend["code"]):
                pend["fails"] += 1
                self._note_fail(source)
                if pend["fails"] >= _MAX_CODE_FAILS:
                    self._pending = None             # BURN the code after too many misses
                return None
            # correct → mint the device, single-use, clear this source's failures
            self._pending = None
            self._src_fails.pop(source, None)
            raw = secrets.token_urlsafe(32)
            device = {
                "id": secrets.token_hex(4),
                "name": (device_name or "phone").strip()[:60] or "phone",
                "token_hash": _hash(raw),
                "created": _now(), "last_seen": None,
                "enabled": True, "scope": "phone",
            }
            data = self._load()
            data["devices"].append(device)
            self._save(data)
            return {"device_id": device["id"], "device_token": raw,  # raw shown ONCE
                    "name": device["name"], "scope": "phone"}

    # ── auth + housekeeping ──────────────────────────────────────────────
    def authenticate(self, token: str) -> Optional[dict]:
        h = _hash(token or "")
        with self._lock:
            for d in self._load().get("devices", []):
                if d.get("enabled") and secrets.compare_digest(d.get("token_hash", ""), h):
                    return d
        return None

    def touch(self, device_id: str) -> None:
        with self._lock:
            data = self._load()
            for d in data.get("devices", []):
                if d.get("id") == device_id:
                    d["last_seen"] = _now()
            self._save(data)

    def list(self) -> list:
        return [{k: d.get(k) for k in ("id", "name", "created", "last_seen", "enabled", "scope")}
                for d in self._load().get("devices", [])]

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            data = self._load()
            before = len(data.get("devices", []))
            data["devices"] = [d for d in data.get("devices", []) if d.get("id") != device_id]
            self._save(data)
            return len(data["devices"]) < before

    def revoke_all(self) -> int:
        with self._lock:
            data = self._load()
            n = len(data.get("devices", []))
            data["devices"] = []
            self._save(data)
            return n


# ── Tailscale status (truthful — never claim reachable when it isn't) ────
def _tailscale_exe() -> Optional[str]:
    """Find the tailscale CLI on PATH OR at the Windows default install path (the
    backend process often doesn't have Program Files\\Tailscale on its PATH, which
    would otherwise make us falsely report 'not installed')."""
    exe = shutil.which("tailscale")
    if exe:
        return exe
    default = Path(r"C:\Program Files\Tailscale\tailscale.exe")
    return str(default) if default.exists() else None


def _tailscale_status() -> dict:
    exe = _tailscale_exe()
    if not exe:
        return {"installed": False, "up": False, "ip": None, "magicdns": None}
    try:
        r = subprocess.run([exe, "status", "--json"], capture_output=True,
                           text=True, timeout=5)
        d = json.loads(r.stdout or "{}")
        me = d.get("Self") or {}
        ips = me.get("TailscaleIPs") or []
        return {"installed": True, "up": d.get("BackendState") == "Running",
                "ip": ips[0] if ips else None,
                "magicdns": (me.get("DNSName") or "").rstrip(".") or None}
    except Exception:
        return {"installed": True, "up": False, "ip": None, "magicdns": None}


def network_status() -> dict:
    return {"remote_enabled": remote_enabled(), "tailscale": _tailscale_status(),
            "paired": len(get_registry().list())}


_registry: Optional[DeviceRegistry] = None
_lock = threading.Lock()


def get_registry() -> DeviceRegistry:
    global _registry
    with _lock:
        if _registry is None:
            _registry = DeviceRegistry()
        return _registry
