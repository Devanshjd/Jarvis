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
