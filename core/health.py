"""
J.A.R.V.I.S — Service Health  (truthful, live probes for /api/status)

Answers "which of my subsystems actually work *right now*" with real probes —
so the UI can show LOCAL BRAIN OFFLINE / VISION UNAVAILABLE / VOICE DISCONNECTED
truthfully instead of a hard-coded "READY". Never claims a service is up unless
a live check says so; reports `error` when it isn't.

Results are cached briefly (TTL) so /api/status polling doesn't hammer probes.

Ownership note: `connected`/`active_source` for renderer-owned subsystems
(Gemini Live WS, the camera the desktop chose) are reported as null here — the
backend genuinely can't see them; the desktop app fills those in.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import threading
import time
from pathlib import Path

_TTL = 8.0
_lock = threading.Lock()
_cache: dict = {"t": 0.0, "data": None}


def _spec(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def _find_tesseract() -> bool:
    if shutil.which("tesseract"):
        return True
    return Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe").exists()


def _probe_ollama() -> dict:
    out = {"reachable": False, "active_model": None, "models": 0, "error": None}
    try:
        import requests
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=3)
        if r.status_code != 200:
            out["error"] = f"HTTP {r.status_code}"
            return out
        out["reachable"] = True
        out["models"] = len(r.json().get("models", []) or [])
        try:
            ps = requests.get("http://127.0.0.1:11434/api/ps", timeout=3)
            loaded = ps.json().get("models", []) if ps.status_code == 200 else []
            out["active_model"] = loaded[0].get("name") if loaded else None
        except Exception:
            pass
    except Exception as e:
        out["error"] = str(e)[:100]
    return out


def _probe_gemini() -> dict:
    key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not key:
        try:
            cfg = Path.home() / ".jarvis_config.json"
            if cfg.exists():
                d = json.loads(cfg.read_text(encoding="utf-8"))
                key = ((d.get("apiKeys") or {}).get("gemini")
                       or (d.get("gemini") or {}).get("api_key") or "").strip()
        except Exception:
            pass
    # `connected` is renderer-owned (the Gemini Live WebSocket lives in the app).
    return {"configured": bool(key), "connected": None, "error": None}


def _probe_vision(ollama: dict) -> dict:
    has_moon = False
    try:
        import requests
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=3)
        if r.status_code == 200:
            has_moon = any("moondream" in (m.get("name") or "")
                           for m in r.json().get("models", []))
    except Exception:
        pass
    available = bool(ollama["reachable"] and has_moon)
    return {
        "available": available,
        "active_model": "moondream" if has_moon else None,
        "ocr": _find_tesseract(),
        "active_source": None,   # renderer-owned (which camera/screen the app chose)
        "error": None if available else "moondream model or ollama unavailable",
    }


def _probe_embedder(ollama: dict) -> dict:
    model = "nomic-embed-text"
    if not ollama["reachable"]:
        return {"available": False, "healthy": False, "model": model, "error": "ollama unreachable"}
    # Only claim unhealthy on a real failure — a slow first embed is the model
    # cold-loading from disk, not a fault. Long timeout + `keep_alive` so the
    # model stays warm; a genuine miss (model absent / bad response) still reports.
    try:
        import requests
        r = requests.post(
            "http://127.0.0.1:11434/api/embeddings",
            json={"model": model, "prompt": "health probe", "keep_alive": "10m"},
            timeout=45)
        if r.status_code == 200 and r.json().get("embedding"):
            return {"available": True, "healthy": True, "model": model, "error": None}
        if r.status_code == 404:
            return {"available": False, "healthy": False, "model": model,
                    "error": "nomic-embed-text not installed (ollama pull nomic-embed-text)"}
        return {"available": True, "healthy": False, "model": model,
                "error": f"HTTP {r.status_code} or empty embedding"}
    except Exception as e:
        # A timeout here almost always means "still loading" — report warming,
        # not a hard failure, so the UI doesn't flash a false red.
        msg = str(e)
        warming = "timed out" in msg.lower() or "read timeout" in msg.lower()
        return {"available": True, "healthy": None if warming else False,
                "model": model,
                "error": "warming up (cold load)" if warming else msg[:100]}


def _probe_stt() -> dict:
    ok = _spec("faster_whisper")
    return {"available": ok, "engine": "faster-whisper", "healthy": ok,
            "error": None if ok else "faster_whisper not importable"}


def _probe_tts() -> dict:
    piper = _spec("piper") or _spec("piper_tts")
    pyt = _spec("pyttsx3")
    ok = bool(piper or pyt)
    return {"available": ok, "engine": "piper" if piper else ("pyttsx3" if pyt else None),
            "healthy": ok, "error": None if ok else "no TTS engine importable"}


def _probe_gesture() -> dict:
    # Gesture runs as a SEPARATE Python 3.11 process (MediaPipe is broken on the
    # 3.13 backend), so the backend cannot import/health-check it directly.
    return {"available": None, "kind": "external process (py3.11 + mediapipe)",
            "healthy": None, "error": None}


def probe_all(force: bool = False) -> dict:
    """Live health of every subsystem. Cached for _TTL seconds."""
    with _lock:
        now = time.time()
        if not force and _cache["data"] is not None and (now - _cache["t"]) < _TTL:
            return _cache["data"]
    ollama = _probe_ollama()
    data = {
        "ollama": ollama,
        "gemini_live": _probe_gemini(),
        "vision": _probe_vision(ollama),
        "memory_embedder": _probe_embedder(ollama),
        "stt": _probe_stt(),
        "tts": _probe_tts(),
        "gesture": _probe_gesture(),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    with _lock:
        _cache["t"] = time.time()
        _cache["data"] = data
    return data
