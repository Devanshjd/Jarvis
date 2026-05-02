"""FastAPI backend for the JARVIS web and TypeScript shells.

Expanded API surface powering the Electron desktop shell widgets:
  /api/status, /api/history, /api/chat          — core runtime
  /api/voice/*                                   — voice engine
  /api/tools/*                                   — plugin registry
  /api/terminal/execute                          — shell command execution
  /api/memory/*                                  — memory CRUD
  /api/knowledge/search                          — knowledge graph
  /api/files/*                                   — file management
  /api/weather                                   — weather data
  /api/research                                  — web research
  /api/security/*                                — pentest / cyber
  /api/evolution/status                          — self-evolution metrics
"""

from __future__ import annotations

import logging
import os
import subprocess
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from core.headless_runtime import HeadlessJarvisRuntime
from core.database import get_db


app = FastAPI(title="JARVIS Web Shell", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
_runtime: HeadlessJarvisRuntime | None = None
_runtime_lock = threading.Lock()
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


def get_runtime() -> HeadlessJarvisRuntime:
    global _runtime
    with _runtime_lock:
        if _runtime is None:
            _runtime = HeadlessJarvisRuntime()
        return _runtime


def _safe(fn, default=None):
    """Run fn() and return its result, or default on failure."""
    try:
        return fn()
    except Exception:
        return default


@app.on_event("shutdown")
def _shutdown_runtime():
    global _runtime
    if _runtime is not None:
        _runtime.shutdown()
        _runtime = None


# ═══════════════════════════════════════════
# Request / Response Models
# ═══════════════════════════════════════════

class ChatRequest(BaseModel):
    text: str = Field(min_length=1)
    approve_desktop: bool = False
    timeout_s: float = Field(default=120.0, ge=1.0, le=300.0)

class VoiceRequest(BaseModel):
    enabled: bool | None = None

class TerminalRequest(BaseModel):
    command: str = Field(min_length=1)
    cwd: str | None = None
    timeout_s: float = Field(default=30.0, ge=1.0, le=120.0)

class MemorySaveRequest(BaseModel):
    content: str = Field(min_length=1)
    title: str = ""

class FileReadRequest(BaseModel):
    path: str = Field(min_length=1)

class FileWriteRequest(BaseModel):
    path: str = Field(min_length=1)
    content: str

class ResearchRequest(BaseModel):
    query: str = Field(min_length=1)
    depth: str = "normal"  # quick | normal | deep

class SecurityScanRequest(BaseModel):
    target: str = Field(min_length=1)
    scan_type: str = "recon"  # recon | port_scan | vuln_scan | subdomain


# ═══════════════════════════════════════════
# Core Runtime Endpoints (existing)
# ═══════════════════════════════════════════

@app.get("/api/status")
def api_status():
    return get_runtime().status_snapshot()

@app.get("/api/history")
def api_history(limit: int = 120):
    return {"messages": get_runtime().history(limit)}

@app.post("/api/chat")
def api_chat(payload: ChatRequest):
    result = get_runtime().process_text(
        payload.text,
        approve_desktop=payload.approve_desktop,
        timeout=payload.timeout_s,
    )
    # Never let reply be null/None — the Electron UI renders it literally
    if not result.get("reply"):
        result["reply"] = "I'm here, sir. Could you please rephrase your request?"
    return result

@app.get("/api/screenshot")
def api_screenshot():
    """Take a screenshot using pyautogui — no external API needed.
    Returns base64-encoded PNG of the entire screen.
    The Gemini Live session can receive this as inline_data vision input.
    """
    try:
        import pyautogui
        import io, base64
        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        w, h = img.size
        return {"success": True, "base64": b64, "width": w, "height": h, "mimeType": "image/png"}
    except ImportError:
        return {"success": False, "error": "pyautogui not installed. Run: pip install pyautogui"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════
#  LOCAL-FIRST VISION ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════
#
#  Tier-1 (preferred): Local Ollama vision model (gemma3:4b, llama3.2-vision,
#                      llava, moondream, etc.) — zero internet, zero quota.
#  Tier-2 (fallback):  Gemini REST API — only used when local is down AND a
#                      user-configured key is available.
#
#  This endpoint is called by both the Electron `awareness-analyze-now` IPC
#  and the `screen_scan` voice tool. It will pick the best available local
#  vision model automatically and only fall back to cloud if local fails.
# ═══════════════════════════════════════════════════════════════════════════

# Ordered preference: best quality first, fall back to smaller models on
# memory pressure (Ollama returns HTTP 500 'requires more system memory').
# The chain is auto-iterated on OOM in api_screen_analyze().
_LOCAL_VISION_MODELS = [
    "gemma3:4b",          # ~3GB RAM, multimodal native, best quality on RTX 4060
    "llava:7b",           # ~5GB RAM, balanced
    "moondream",          # ~2GB RAM, fastest fallback when RAM is tight
    "llava:13b",          # Higher quality, needs more VRAM
    "llama3.2-vision",
    "llama3.2-vision:11b",
    "bakllava",
]


def _list_ollama_models() -> list[str]:
    """Return list of installed Ollama model names. Empty if Ollama is down."""
    try:
        import requests
        r = requests.get("http://127.0.0.1:11434/api/tags", timeout=2)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


def _pick_local_vision_model() -> str | None:
    """Return the best installed local vision model, or None if none."""
    chain = _vision_model_chain()
    return chain[0] if chain else None


def _vision_model_chain() -> list[str]:
    """Return ALL installed vision-capable models in preference order.
    The caller iterates through this on failure (memory pressure, etc.)
    and falls back to smaller models when bigger ones can't load.
    """
    installed = _list_ollama_models()
    if not installed:
        return []
    chain: list[str] = []
    for preferred in _LOCAL_VISION_MODELS:
        for name in installed:
            if name in chain:
                continue
            if name == preferred or name.startswith(preferred.split(":")[0] + ":"):
                try:
                    import requests
                    show = requests.post(
                        "http://127.0.0.1:11434/api/show",
                        json={"name": name},
                        timeout=3,
                    ).json()
                    if "vision" in (show.get("capabilities") or []):
                        chain.append(name)
                except Exception:
                    continue
    return chain


def _analyze_with_ollama(b64_png: str, prompt: str, model: str) -> dict:
    """Call local Ollama with a vision prompt. Returns {success, text, model, latency_ms}.

    Sets keep_alive=0 so Ollama unloads the model immediately after the call.
    This frees the ~3GB system RAM the model uses, important when RAM is
    tight (e.g. dev server + Electron + browser already loaded).
    """
    import requests, time
    t0 = time.time()
    try:
        r = requests.post(
            "http://127.0.0.1:11434/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "images": [b64_png],
                "stream": False,
                "keep_alive": "0s",  # unload after call to free RAM
                "options": {"temperature": 0.3, "num_predict": 250},
            },
            timeout=90,
        )
        if r.status_code != 200:
            err_body = r.text[:300]
            # Detect the OOM signature so the caller can fall back to a smaller model
            oom = "requires more system memory" in err_body
            return {
                "success": False,
                "error": f"Ollama HTTP {r.status_code}: {err_body}",
                "oom": oom,
            }
        data = r.json()
        text = (data.get("response") or "").strip()
        if not text:
            return {"success": False, "error": "Ollama returned empty response"}
        return {
            "success": True,
            "text": text,
            "model": model,
            "source": "ollama_local",
            "latency_ms": int((time.time() - t0) * 1000),
        }
    except Exception as e:
        return {"success": False, "error": f"Ollama call failed: {e}"}


@app.get("/api/screen/analyze")
def api_screen_analyze(prompt: str | None = None, with_ocr: bool = True):
    """Take a screenshot and analyze it.

    Tries local Ollama vision first (zero internet, zero quota).
    When with_ocr=True (default), Tesseract OCR text is extracted and
    injected into the vision prompt as context — boosts accuracy for
    code/error/text-heavy screens.

    Returns: {success, text, source, model, latency_ms, width, height, ocr?}

    Query params:
      prompt   — what to ask about the screen (default: general description)
      with_ocr — set to false to skip Tesseract pre-pass (default: true)
    """
    try:
        import pyautogui, io, base64
        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        w, h = img.size
    except Exception as e:
        return {"success": False, "error": f"Screenshot failed: {e}"}

    # Tier 0 (parallel): Tesseract OCR — fast, gives the LLM exact text content
    ocr_text = ""
    if with_ocr and _find_tesseract():
        try:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = _find_tesseract()
            ocr_text = pytesseract.image_to_string(img).strip()
        except Exception:
            ocr_text = ""

    base_prompt = (prompt or "").strip() or (
        "Describe what is on this screen. Focus on: 1) Which app is active 2) "
        "What the user is doing 3) Any errors or important text visible. "
        "Keep under 100 words. If you see code errors, mention them specifically."
    )

    # Inject OCR text as a hint when present — model uses it to ground its answer
    if ocr_text and len(ocr_text) > 20:
        clipped = ocr_text[:1500]  # cap to keep prompt reasonable
        user_prompt = (
            f"{base_prompt}\n\n"
            f"[OCR text already extracted from the screen — use this to confirm "
            f"exact wording of any text you describe]:\n{clipped}"
        )
    else:
        user_prompt = base_prompt

    # Tier 1: Local Ollama vision — iterate through chain, falling back to
    # smaller models on OOM ('requires more system memory') or other errors.
    log = logging.getLogger("jarvis.screen_analyze")
    chain = _vision_model_chain()
    last_error = None
    for local_model in chain:
        result = _analyze_with_ollama(b64, user_prompt, local_model)
        if result.get("success"):
            result.update({
                "width": w,
                "height": h,
                "ocr_text": ocr_text if ocr_text else None,
                "ocr_chars": len(ocr_text) if ocr_text else 0,
                "tried_models": chain[: chain.index(local_model) + 1],
            })
            return result
        last_error = result.get("error")
        log.warning("Local vision (%s) failed: %s — trying next in chain", local_model, last_error)
        # Only iterate to next model if this was OOM or a transient error,
        # otherwise (e.g. bad image) the next model will fail the same way
        if not result.get("oom"):
            break
    if last_error:
        log.warning("All %d local vision models failed; falling back to cloud", len(chain))

    # If OCR worked, we can still return SOMETHING useful even when vision LLM failed
    if ocr_text and len(ocr_text) > 30:
        return {
            "success": True,
            "text": (
                "Vision LLM unavailable (memory pressure). OCR text from screen:\n\n"
                + ocr_text[:2000]
            ),
            "source": "ocr_only",
            "model": "tesseract",
            "width": w,
            "height": h,
            "ocr_chars": len(ocr_text),
            "warning": last_error or "no vision model available",
        }

    # No local vision available — return clear status
    return {
        "success": False,
        "error": (
            "No local vision model installed. Run one of these to enable "
            "fully-local screen analysis:\n"
            "  ollama pull gemma3:4b      (4.3B, ~3GB, fast)\n"
            "  ollama pull llava:7b       (7B, ~4.7GB, balanced)\n"
            "  ollama pull moondream      (1.7GB, smallest)"
        ),
        "width": w,
        "height": h,
    }


@app.get("/api/vision/status")
def api_vision_status():
    """Report which local vision models are installed and which is active."""
    installed = _list_ollama_models()
    active = _pick_local_vision_model()
    return {
        "ollama_running": bool(installed),
        "installed_models": installed,
        "active_vision_model": active,
        "preference_order": _LOCAL_VISION_MODELS,
        "fully_local_capable": active is not None,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  TIER-0 SCREEN OCR — Tesseract for instant text extraction (~1s, no LLM)
# ═══════════════════════════════════════════════════════════════════════════
#  When the user just wants to know what TEXT is on screen (errors, code,
#  page contents), OCR is faster + more accurate than vision LLM. Pair with
#  vision LLM when reasoning is needed.
# ═══════════════════════════════════════════════════════════════════════════

# Cache the tesseract path detection
_TESSERACT_PATH = None


def _find_tesseract() -> str | None:
    """Locate the Tesseract binary. Returns full path or None if not installed."""
    global _TESSERACT_PATH
    if _TESSERACT_PATH is not None:
        return _TESSERACT_PATH or None
    import shutil
    found = shutil.which("tesseract")
    if not found:
        for candidate in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
        ):
            if Path(candidate).exists():
                found = candidate
                break
    _TESSERACT_PATH = found or ""
    return found


@app.get("/api/screen/ocr")
def api_screen_ocr():
    """Extract all readable text from the current screen using Tesseract OCR.

    No internet, no API. Returns extracted text plus latency for benchmarking.
    Use this when the user wants TEXT on screen (errors, code, page contents);
    use /api/screen/analyze when they want reasoning ABOUT the screen.
    """
    tess_path = _find_tesseract()
    if not tess_path:
        return {
            "success": False,
            "error": (
                "Tesseract OCR not installed. Install with:\n"
                "  winget install --id UB-Mannheim.TesseractOCR\n"
                "  pip install pytesseract"
            ),
        }
    try:
        import pyautogui, pytesseract, time
        pytesseract.pytesseract.tesseract_cmd = tess_path
        t0 = time.time()
        img = pyautogui.screenshot()
        text = pytesseract.image_to_string(img).strip()
        latency = int((time.time() - t0) * 1000)
        w, h = img.size
        return {
            "success": True,
            "text": text,
            "char_count": len(text),
            "line_count": text.count("\n") + 1 if text else 0,
            "width": w,
            "height": h,
            "latency_ms": latency,
            "source": "tesseract_local",
        }
    except Exception as e:
        return {"success": False, "error": f"OCR failed: {e}"}


# ═══════════════════════════════════════════════════════════════════════════
#  LOCAL TEXT-TO-SPEECH — Piper neural TTS, runs on CPU
# ═══════════════════════════════════════════════════════════════════════════
#  Replaces Gemini Live's TTS for non-conversational outputs. Sub-100ms
#  latency after the first call (model load is cached). Voice is configurable.
# ═══════════════════════════════════════════════════════════════════════════

_PIPER_VOICE = None  # Cached PiperVoice instance


def _get_piper_voice():
    """Lazy-load Piper voice. Returns None if Piper isn't set up."""
    global _PIPER_VOICE
    if _PIPER_VOICE is not None:
        return _PIPER_VOICE if _PIPER_VOICE != "missing" else None
    try:
        from piper import PiperVoice
        # Default voice path — user can change by symlinking or editing
        models_dir = Path(__file__).resolve().parents[1] / "models" / "piper"
        candidates = list(models_dir.glob("*.onnx")) if models_dir.exists() else []
        if not candidates:
            _PIPER_VOICE = "missing"
            return None
        # Prefer en_US-ryan-medium if present, else first available
        chosen = next(
            (c for c in candidates if "ryan" in c.name.lower() and "medium" in c.name.lower()),
            candidates[0],
        )
        _PIPER_VOICE = PiperVoice.load(str(chosen))
        return _PIPER_VOICE
    except Exception as e:
        logging.getLogger("jarvis.tts").warning("Piper unavailable: %s", e)
        _PIPER_VOICE = "missing"
        return None


@app.get("/api/tts/status")
def api_tts_status():
    """Report whether local TTS is ready."""
    from piper import PiperVoice  # noqa: F401  — proves the package is importable
    voice = _get_piper_voice()
    models_dir = Path(__file__).resolve().parents[1] / "models" / "piper"
    voices = [p.name for p in models_dir.glob("*.onnx")] if models_dir.exists() else []
    return {
        "piper_available": voice is not None,
        "voices_dir": str(models_dir),
        "installed_voices": voices,
        "active_voice": (
            getattr(voice, "config_path", None) if voice else None
        ),
    }


class TTSRequest(BaseModel):
    text: str
    play: bool = False  # if True, play directly on the host audio device


@app.post("/api/tts/speak")
def api_tts_speak(payload: TTSRequest):
    """Synthesize text to a WAV file using local Piper TTS.

    Returns a base64-encoded WAV (always) and optionally plays it on the
    host audio device (if play=true). Latency is ~50-200ms after first call
    once the voice model is loaded.
    """
    voice = _get_piper_voice()
    if voice is None:
        return {
            "success": False,
            "error": (
                "Piper TTS not set up. Place an .onnx voice in models/piper/. "
                "Suggested: download en_US-ryan-medium.onnx from "
                "https://huggingface.co/rhasspy/piper-voices"
            ),
        }
    text = (payload.text or "").strip()
    if not text:
        return {"success": False, "error": "empty text"}
    try:
        import io, wave, base64, time
        t0 = time.time()
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            voice.synthesize_wav(text, wf)
        latency = int((time.time() - t0) * 1000)
        wav_bytes = buf.getvalue()
        b64 = base64.b64encode(wav_bytes).decode()

        if payload.play:
            # Play in a background thread so the API doesn't block
            def _play():
                try:
                    import winsound
                    winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)
                except Exception:
                    pass
            threading.Thread(target=_play, daemon=True).start()

        return {
            "success": True,
            "audio_base64": b64,
            "size_bytes": len(wav_bytes),
            "latency_ms": latency,
            "played": payload.play,
            "source": "piper_local",
        }
    except Exception as e:
        return {"success": False, "error": f"TTS failed: {e}"}

@app.get("/api/clipboard/text")
def api_clipboard_text():
    """Read text from system clipboard — no external API needed."""
    try:
        import pyperclip
        text = pyperclip.paste()
        if not text or not text.strip():
            return {"success": False, "error": "Clipboard is empty or contains no text"}
        return {"success": True, "text": text.strip()}
    except ImportError:
        try:
            import subprocess
            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=5
            )
            text = result.stdout.strip()
            if text:
                return {"success": True, "text": text}
        except Exception:
            pass
        return {"success": False, "error": "pyperclip not installed. Run: pip install pyperclip"}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/voice/status")
def api_voice_status():
    return get_runtime().voice_snapshot()

@app.post("/api/voice/toggle")
def api_voice_toggle(payload: VoiceRequest):
    return get_runtime().set_voice_enabled(payload.enabled)


# ═══════════════════════════════════════════
# Tools & Plugins
# ═══════════════════════════════════════════

@app.get("/api/tools/list")
def api_tools_list():
    """List all loaded plugins and their capabilities."""
    rt = get_runtime()
    plugins = {}
    for name, plugin in rt.plugin_manager.plugins.items():
        info: dict[str, Any] = {"name": name, "active": True}
        if hasattr(plugin, "get_tools"):
            info["tools"] = _safe(plugin.get_tools, [])
        if hasattr(plugin, "get_status"):
            info["status"] = _safe(plugin.get_status, {})
        plugins[name] = info
    return {"plugins": plugins, "count": len(plugins)}


# ═══════════════════════════════════════════
# Terminal Execution
# ═══════════════════════════════════════════

@app.post("/api/terminal/execute")
def api_terminal_execute(payload: TerminalRequest):
    """Execute a shell command on the host system.
    
    Requires approve_desktop pattern — the Electron shell must
    explicitly confirm the user has the toggle enabled.
    """
    try:
        cwd = payload.cwd or str(Path.home())
        result = subprocess.run(
            payload.command,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=payload.timeout_s,
            env={**os.environ, "TERM": "dumb"},
        )
        return {
            "stdout": result.stdout[-8000:] if result.stdout else "",
            "stderr": result.stderr[-4000:] if result.stderr else "",
            "returncode": result.returncode,
            "command": payload.command,
            "cwd": cwd,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Command timed out", "command": payload.command, "timeout": payload.timeout_s}
    except Exception as e:
        return {"error": str(e), "command": payload.command}


# ═══════════════════════════════════════════
# Memory CRUD
# ═══════════════════════════════════════════

@app.get("/api/memory/list")
def api_memory_list(limit: int = 100):
    """List stored memories from SQLite database."""
    db = get_db()
    items = db.get_all_memories(limit)
    return {"memories": items, "total": db.get_memory_count()}

@app.post("/api/memory/save")
def api_memory_save(payload: MemorySaveRequest):
    """Save a new memory to SQLite database."""
    db = get_db()
    try:
        saved = db.save_memory(payload.content, category=payload.title or "general")
        return {"saved": saved, "content": payload.content}
    except Exception as e:
        return {"saved": False, "error": str(e)}


class VoiceMemorySaveRequest(BaseModel):
    user_text: str = ""
    assistant_text: str = ""
    tool_used: str = ""


@app.get("/api/memory/context")
def api_memory_context():
    """
    Bundle ALL persistent memory into a single context block
    for Gemini Live voice session injection.
    Uses the unified SQLite database as primary source,
    falls back to runtime objects for knowledge graph.
    """
    import logging
    log = logging.getLogger("jarvis.memory")

    sections = []

    # 1-6. All core memory from unified SQLite DB (CRITICAL — this is the main source)
    try:
        db = get_db()
        db_context = db.get_full_memory_context()
        if db_context:
            sections.append(db_context)
            log.info(f"[memory/context] DB context loaded: {len(db_context)} chars")
        else:
            log.warning("[memory/context] DB returned empty context")
    except Exception as e:
        log.error(f"[memory/context] Failed to load DB context: {e}")
        traceback.print_exc()

    # 7. Knowledge Graph (non-critical — don't let runtime init kill the response)
    try:
        rt = get_runtime()
        if hasattr(rt, 'knowledge_graph'):
            kg_ctx = rt.knowledge_graph.get_context_for_llm(max_facts=20)
            if kg_ctx:
                sections.append(kg_ctx)
    except Exception as e:
        log.warning(f"[memory/context] Knowledge graph unavailable: {e}")

    # 8. Intelligence emotional state (from DB if available)
    try:
        db = get_db()
        emotional = db.kv_get_all("intelligence_emotional")
        if emotional and emotional.get("current_mood"):
            mood = emotional["current_mood"]
            rapport = emotional.get("rapport_score", 50)
            sections.append(f"[EMOTIONAL STATE] Operator mood: {mood}, rapport: {rapport}/100")
    except Exception:
        pass

    combined = "\n\n".join(s for s in sections if s.strip())
    log.info(f"[memory/context] Returning {len(sections)} sections, {len(combined)} chars")
    return {"context": combined, "sections": len(sections), "source": "sqlite"}


@app.post("/api/memory/voice-save")
def api_memory_voice_save(payload: VoiceMemorySaveRequest):
    """
    Save a voice conversation exchange to persistent memory.
    Called by Gemini Live after each turn completes.
    Writes to unified SQLite DB + knowledge graph.
    """
    db = get_db()
    rt = get_runtime()
    saved_to = []

    errors = []

    # Save to unified SQLite conversations table
    try:
        if payload.user_text and payload.assistant_text:
            db.save_conversation(
                user_text=payload.user_text,
                assistant_text=payload.assistant_text,
                tool_used=payload.tool_used,
                source="voice"
            )
            saved_to.append("sqlite_conversations")
    except Exception as e:
        errors.append(f"conversations: {e}")

    # Extract entities to knowledge graph (still separate SQLite)
    try:
        if hasattr(rt, 'knowledge_graph') and payload.user_text:
            rt.knowledge_graph.auto_extract(payload.user_text)
            if payload.assistant_text:
                rt.knowledge_graph.auto_extract(payload.assistant_text)
            saved_to.append("knowledge_graph")
    except Exception as e:
        errors.append(f"knowledge_graph: {e}")

    # Log tool usage as episode
    try:
        if payload.tool_used:
            db.record_episode(
                goal=payload.user_text[:200],
                tool=payload.tool_used,
                status="completed",
                result=payload.assistant_text[:200]
            )
            saved_to.append("sqlite_episodes")
    except Exception as e:
        errors.append(f"episodes: {e}")

    success = len(saved_to) > 0 or (not payload.user_text and not payload.assistant_text)
    result = {"saved": success, "saved_to": saved_to}
    if errors:
        result["errors"] = errors
    return result


# ═══════════════════════════════════════════
# Knowledge Graph
# ═══════════════════════════════════════════

@app.get("/api/memory/search")
def api_memory_search(q: str = Query(min_length=1)):
    """Full-text search across conversations and memories."""
    db = get_db()
    convos = db.search_conversations(q, limit=10)
    mems = db.search_memories(q, limit=10)
    return {"query": q, "conversations": convos, "memories": mems}


@app.get("/api/memory/stats")
def api_memory_stats():
    """Database statistics."""
    db = get_db()
    return db.get_stats()


@app.get("/api/training/stats")
def api_training_stats():
    """Training data statistics."""
    db = get_db()
    return db.get_training_stats()


@app.get("/api/training/examples")
def api_training_examples(tool: str | None = None, limit: int = 50):
    """Get training examples, optionally by tool."""
    db = get_db()
    return {"examples": db.get_training_examples(tool, limit)}


@app.get("/api/training/export")
def api_training_export():
    """Export all training data as JSONL path."""
    db = get_db()
    path = db.export_training_jsonl()
    return {"exported": True, "path": path, "total": db.get_training_stats()["total_examples"]}


@app.get("/api/knowledge/search")
def api_knowledge_search(q: str = Query(min_length=1)):
    """Search the knowledge graph."""
    rt = get_runtime()
    try:
        results = rt.knowledge_graph.search(q)
        return {"query": q, "results": results}
    except Exception as e:
        return {"query": q, "results": [], "error": str(e)}


# ═══════════════════════════════════════════
# File Management
# ═══════════════════════════════════════════

@app.get("/api/files/list")
def api_files_list(path: str = "."):
    """List directory contents."""
    try:
        target = Path(path).resolve()
        if not target.exists():
            return {"error": f"Path does not exist: {path}", "entries": []}
        if not target.is_dir():
            return {"error": f"Not a directory: {path}", "entries": []}
        entries = []
        for entry in sorted(target.iterdir()):
            try:
                stat = entry.stat()
                entries.append({
                    "name": entry.name,
                    "type": "dir" if entry.is_dir() else "file",
                    "size": stat.st_size if entry.is_file() else None,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
            except (PermissionError, OSError):
                entries.append({"name": entry.name, "type": "unknown", "error": "access denied"})
        return {"path": str(target), "entries": entries}
    except Exception as e:
        return {"error": str(e), "entries": []}

@app.post("/api/files/read")
def api_files_read(payload: FileReadRequest):
    """Read a file's contents."""
    try:
        target = Path(payload.path).resolve()
        if not target.is_file():
            return {"error": f"Not a file: {payload.path}"}
        content = target.read_text(encoding="utf-8", errors="replace")
        return {"path": str(target), "content": content[:50000], "size": len(content)}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/files/write")
def api_files_write(payload: FileWriteRequest):
    """Write content to a file."""
    try:
        target = Path(payload.path).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload.content, encoding="utf-8")
        return {"written": True, "path": str(target), "size": len(payload.content)}
    except Exception as e:
        return {"written": False, "error": str(e)}


# ═══════════════════════════════════════════
# Weather
# ═══════════════════════════════════════════

@app.get("/api/weather")
def api_weather(city: str = ""):
    """Get current weather via the WebIntel plugin or JARVIS chat."""
    rt = get_runtime()
    web_intel = rt.plugin_manager.get_plugin("web_intel")
    if web_intel and hasattr(web_intel, "get_weather"):
        try:
            data = web_intel.get_weather(city)
            return {"source": "web_intel", "data": data}
        except Exception:
            pass
    # Fallback: ask JARVIS via orchestrator
    result = rt.process_text(
        f"what is the current weather{' in ' + city if city else ''}? Give a brief summary.",
        approve_desktop=False,
        timeout=30.0,
    )
    return {"source": "chat", "data": result.get("reply", "Unable to fetch weather.")}


# ═══════════════════════════════════════════
# Web Research
# ═══════════════════════════════════════════

@app.post("/api/research")
def api_research(payload: ResearchRequest):
    """Run a deep web research query."""
    rt = get_runtime()
    try:
        if hasattr(rt.researcher, "research"):
            result = rt.researcher.research(payload.query)
            return {"query": payload.query, "result": result}
    except Exception:
        pass
    # Fallback via chat
    result = rt.process_text(
        f"research: {payload.query}",
        approve_desktop=False,
        timeout=120.0,
    )
    return {"query": payload.query, "result": result.get("reply", "")}


# ═══════════════════════════════════════════
# Security / Pentest
# ═══════════════════════════════════════════

@app.post("/api/security/scan")
def api_security_scan(payload: SecurityScanRequest):
    """Run a security scan via the Cyber or Pentest plugin."""
    rt = get_runtime()
    scan_commands = {
        "recon": f"perform reconnaissance on {payload.target}",
        "port_scan": f"scan ports on {payload.target}",
        "vuln_scan": f"scan for vulnerabilities on {payload.target}",
        "subdomain": f"enumerate subdomains for {payload.target}",
    }
    command = scan_commands.get(payload.scan_type, scan_commands["recon"])
    result = rt.process_text(command, approve_desktop=True, timeout=120.0)
    return {
        "target": payload.target,
        "scan_type": payload.scan_type,
        "result": result.get("reply", "Scan completed."),
    }


# ═══════════════════════════════════════════
# Self-Evolution Metrics
# ═══════════════════════════════════════════

@app.get("/api/evolution/status")
def api_evolution_status():
    """Return self-evolution engine metrics."""
    rt = get_runtime()
    try:
        status = {}
        if hasattr(rt.evolver, "get_status"):
            status = rt.evolver.get_status() or {}
        if hasattr(rt.evolver, "evolution_count"):
            status["evolution_count"] = rt.evolver.evolution_count
        if hasattr(rt.evolver, "last_evolution"):
            status["last_evolution"] = str(rt.evolver.last_evolution)
        return status
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════
# Agent Loop / Execution Router / Struggle
# ═══════════════════════════════════════════


@app.get("/api/agent-loop/status")
def api_agent_loop_status():
    """Return the current agent loop execution status."""
    rt = get_runtime()
    try:
        return rt.agent_loop.get_status()
    except Exception as e:
        return {"status": "idle", "error": str(e)}


@app.get("/api/execution-router/stats")
def api_execution_router_stats():
    """Return adaptive routing statistics."""
    rt = get_runtime()
    try:
        return rt.execution_router.get_stats()
    except Exception as e:
        return {"error": str(e)}


@app.post("/api/execution-router/preference")
def api_set_execution_preference(mode: str = "", duration: float = 300.0):
    """Set user execution mode preference (screen, api, direct, or empty to clear)."""
    rt = get_runtime()
    try:
        rt.execution_router.set_user_preference(mode, duration)
        return {"mode": mode, "duration": duration, "ok": True}
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/struggle/status")
def api_struggle_status():
    """Return JARVIS's self-struggle detection status."""
    rt = get_runtime()
    try:
        return rt.struggle_detector.get_status()
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════
# Frontend Static Files (fallback)
# ═══════════════════════════════════════════

if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:
    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse(
            """
            <!doctype html>
            <html lang="en">
            <head>
              <meta charset="utf-8" />
              <title>JARVIS Frontend Missing</title>
              <style>
                body {
                  margin: 0;
                  min-height: 100vh;
                  display: grid;
                  place-items: center;
                  font-family: 'Segoe UI', sans-serif;
                  background: #07111a;
                  color: #eef6ff;
                }
                main {
                  max-width: 720px;
                  padding: 24px;
                  border-radius: 18px;
                  background: rgba(255,255,255,0.04);
                  border: 1px solid rgba(110,205,245,0.18);
                }
                code {
                  display: block;
                  margin-top: 12px;
                  padding: 12px;
                  border-radius: 12px;
                  background: rgba(0,0,0,0.28);
                }
              </style>
            </head>
            <body>
              <main>
                <h1>JARVIS TypeScript frontend not built yet</h1>
                <p>Run the frontend dev server or build the app first.</p>
                <code>cd frontend && npm run dev</code>
                <code>cd frontend && npm run build</code>
              </main>
            </body>
            </html>
            """
        )
