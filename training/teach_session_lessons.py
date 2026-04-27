"""
JARVIS — Teach lessons learned in the 2026-04-26 debugging session.

Captures every bug we diagnosed + how we fixed it, then writes them into
three learning surfaces so JARVIS can recall and reproduce the diagnostic
reasoning later:

  1. Knowledge graph (core/knowledge_graph.py) — for retrieval at runtime
  2. Learning log (training/learning_log.jsonl) — for future fine-tunes
  3. Tool routing dataset (training/datasets/jarvis_tool_routing/) — SFT pairs

Run with:  python training/teach_session_lessons.py
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.knowledge_graph import KnowledgeGraph  # noqa: E402

LEARN_LOG = ROOT / "training" / "learning_log.jsonl"
SFT_LOG = ROOT / "training" / "datasets" / "jarvis_tool_routing" / "jarvis_tool_routing_sft.jsonl"
LESSONS_MD = ROOT / "training" / "session_lessons_2026-04-26.md"


# ─── 1. Diagnostic lessons (knowledge graph entities) ─────────────────────────
LESSONS: list[dict] = [
    {
        "name": "memory_poisoning_capability_failure",
        "type": "bug_pattern",
        "facts": {
            "symptom": "JARVIS says 'as noted previously' or refuses a capability that should work",
            "root_cause": "Old assistant failure messages got stored in conversations table and injected into every new voice session as 'past exchanges from previous sessions', poisoning the model's beliefs",
            "diagnosis": "Query /api/memory/context and grep for 'API key', 'unavailable', 'failed' phrases in the assistant_text field",
            "fix_location": "core/database.py get_conversations_context()",
            "fix": "Filter assistant_text against _MEMORY_POISON_PATTERNS list before injecting; widen fetch limit so filtering doesn't shrink context",
            "purge_command": "DELETE FROM conversations WHERE assistant_text LIKE '%No API key%' OR LIKE '%unavailable%'",
            "tags": "memory, poisoning, gemini-live, conversation-history",
        },
    },
    {
        "name": "wrong_gemini_api_key_path",
        "type": "bug_pattern",
        "facts": {
            "symptom": "Vision/screen tools return 'No Gemini API key' but voice (Gemini Live) works fine",
            "root_cause": "Config stores key at config.gemini.api_key but old IPC handlers read config.geminiApiKey (camelCase, top-level) which doesn't exist",
            "diagnosis": "Check ~/.jarvis_config.json structure; voice path used correct nested path while 4 vision IPC handlers used wrong path",
            "fix_location": "desktop/src/main/index.ts lines 2456, 2505, 2750, 3165",
            "fix": "Read with fallback chain: config.gemini?.api_key || config.api_key || config.geminiApiKey",
            "tags": "config, api-key, electron-ipc, vision",
        },
    },
    {
        "name": "gemini_free_tier_quota_exhausted",
        "type": "bug_pattern",
        "facts": {
            "symptom": "HTTP 429 from generativelanguage.googleapis.com with 'limit: 0' on gemini-2.0-flash",
            "root_cause": "Free tier RPD (requests per day) for gemini-2.0-flash is 0 on most accounts; awareness loop hammering the endpoint every 15s burns quota and logs failures into memory",
            "diagnosis": "GET https://ai.google.dev/rate-limit dashboard or smoke-test the endpoint with a tiny PNG and the configured key",
            "fix_location": "desktop/src/main/index.ts analyzeScreen()",
            "fix": "Try gemini-2.5-flash first (separate higher quota), fall back to 2.0-flash; on 429 from all models, set awarenessQuotaExhausted=true and stop the loop",
            "better_fix": "Switch to local Ollama vision (gemma3:4b) — eliminates quota dependency entirely",
            "tags": "quota, gemini-rest, billing, free-tier",
        },
    },
    {
        "name": "local_first_vision_via_ollama",
        "type": "architecture_pattern",
        "facts": {
            "principle": "Always try local before cloud for tasks where local capability exists",
            "implementation": "Three-tier chain: Ollama vision -> Gemini Live (if session open) -> Gemini REST",
            "vision_capable_models": "gemma3:4b (multimodal native, 4.3B, ~3GB VRAM), llava:7b, llama3.2-vision:11b, moondream",
            "vision_check_method": "POST /api/show with model name; check response.capabilities for 'vision'",
            "endpoint": "GET /api/screen/analyze on Python backend",
            "performance_rtx4060": "2-7 seconds for screen analysis with gemma3:4b",
            "benefits": "Zero internet, zero quota, $0 per call, works offline",
            "tags": "local-first, ollama, vision, offline, privacy",
        },
    },
    {
        "name": "screen_capture_pyautogui_no_api",
        "type": "architecture_pattern",
        "facts": {
            "principle": "Screen capture is a local OS operation — no API ever needed",
            "implementation": "pyautogui.screenshot() returns PIL Image; encode to base64 PNG; send via existing channel",
            "pitfall": "Old code called Gemini Vision REST for both capture AND analysis — only analysis needs an LLM",
            "endpoint": "GET /api/screenshot returns base64 PNG",
            "live_session_injection": "JarvisGeminiLive.sendImageToSession() pushes via realtimeInput.mediaChunks (same channel as camera/screen stream)",
            "tags": "screenshot, pyautogui, local, vision-input",
        },
    },
    {
        "name": "missing_brain_method_analyze_image",
        "type": "bug_pattern",
        "facts": {
            "symptom": "'Brain' object has no attribute 'analyze_image' when /api/chat receives screen-related input",
            "root_cause": "core/runtime.py scan_screen() called brain.analyze_image() which was deprecated/removed",
            "diagnosis": "POST /api/chat with 'check my screen' -> check the assistant message for AttributeError",
            "fix_location": "core/runtime.py scan_screen()._do_scan",
            "fix": "Replace brain.analyze_image() with new _local_first_vision_analyze() helper that wraps Ollama with cloud fallback",
            "tags": "python, runtime, brain-api, screen-scan",
        },
    },
    {
        "name": "stale_tool_declarations_drift",
        "type": "bug_pattern",
        "facts": {
            "symptom": "Voice JARVIS says 'I don't have a tool for that' when tool exists; or model never tries a capability",
            "root_cause": "Tool declared in switch handler but missing from generatedToolDeclarations.json that Gemini Live reads at session start",
            "diagnosis": "Compare tools listed in JarvisGeminiLive.ts switch cases against names in generatedToolDeclarations.json",
            "fix_location": "Run python core/tool_export.py to regenerate JSON from canonical TOOL_SCHEMAS",
            "fix": "Always update core/tool_schemas.py first; run tool_export.py; rebuild Electron",
            "tags": "tool-declarations, drift, gemini-live, codegen",
        },
    },
    {
        "name": "async_screen_scan_returns_initiated_only",
        "type": "behavior_pattern",
        "facts": {
            "symptom": "Typing 'check my screen' returns 'Screen scan initiated.' but no actual analysis",
            "root_cause": "scan_screen kicks off background thread and returns immediately; chat API doesn't wait for thread to complete",
            "diagnosis": "Check chat history a few seconds after the initial response — the actual analysis arrives as a delayed assistant message",
            "current_behavior": "Result lands in chat history asynchronously, visible in transcript",
            "future_improvement": "For voice, await the result inline before responding so JARVIS speaks the analysis directly",
            "tags": "async, threading, screen-scan, ux",
        },
    },
]


# ─── 2. Q&A pairs for fine-tune learning log ──────────────────────────────────
DIAGNOSTIC_QA: list[tuple[str, str, str]] = [
    # (user question, source/category, expected reasoning/answer)
    (
        "JARVIS keeps saying screen analysis is unavailable even though I have a Gemini key configured",
        "diagnostic",
        "Two likely causes: (1) memory poisoning — old failure messages from conversation history get injected into new sessions. Check /api/memory/context for 'unavailable' phrases. (2) wrong key path — IPC handlers reading config.geminiApiKey instead of config.gemini.api_key. Fix: filter poison phrases in get_conversations_context() and use fallback chain config.gemini?.api_key || config.api_key.",
    ),
    (
        "Why does voice work but vision tools say no API key",
        "diagnostic",
        "Voice and vision read the API key from different paths. Voice uses config.gemini?.api_key (correct nested path) but vision IPC handlers historically used config.geminiApiKey (camelCase, doesn't exist in standard config). Fix all 4 IPC handlers in desktop/src/main/index.ts to use the fallback chain.",
    ),
    (
        "How do I know if my Gemini quota is exhausted",
        "diagnostic",
        "Smoke-test with curl/python POST to https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=YOUR_KEY. HTTP 429 with 'limit: 0' means free tier exhausted. Or check https://ai.google.dev/rate-limit dashboard.",
    ),
    (
        "How can I make screen analysis work without Gemini API",
        "architecture",
        "Use Ollama with a vision-capable model. gemma3:4b is multimodal and runs in ~3GB VRAM. Endpoint: GET /api/screen/analyze on Python backend uses pyautogui for capture and Ollama /api/generate for analysis. Zero internet, zero quota.",
    ),
    (
        "Which Ollama models support vision",
        "knowledge",
        "Check via POST /api/show with the model name and look for 'vision' in the response.capabilities array. Currently vision-capable: gemma3:4b (multimodal native), llava:7b, llava:13b, llama3.2-vision:11b, moondream, bakllava. Text-only: llama3.2, gemma2, jarvis-brain.",
    ),
    (
        "JARVIS keeps reconnecting after a research call",
        "diagnostic",
        "The research IPC call hangs longer than Gemini Live's server-side keepalive timeout. Wrap api.jarvisResearch() in a 20s Promise.race timeout in JarvisGeminiLive.ts so failed research returns gracefully instead of dropping the WebSocket.",
    ),
    (
        "I see 'null' as a JARVIS response in the transcript",
        "diagnostic",
        "Backend /api/chat returned reply: null and the renderer rendered it literally. Two-part fix: (1) server.py — coerce null reply to a placeholder before responding. (2) DashboardView.tsx — filter messages where text is null/empty before rendering.",
    ),
    (
        "Paste isn't working in the JARVIS input box",
        "diagnostic",
        "Electron's clipboard security context can block native Ctrl+V in some configurations. Add an explicit onPaste handler to the textarea that calls e.clipboardData.getData('text') and inserts at the cursor position.",
    ),
    (
        "What's the fastest way to read text on my screen",
        "architecture",
        "Tesseract OCR is ~50ms vs ~2s for a vision LLM, and more accurate for pure text. Use it as Tier 0 above the vision LLM. For 'describe what's on screen' queries that need reasoning, pair OCR text + image to gemma3:4b.",
    ),
    (
        "How do I check what Gemini Live tools JARVIS knows about",
        "knowledge",
        "Read desktop/src/renderer/src/services/generatedToolDeclarations.json — that's what's pushed to the Gemini Live setup turn. If a tool isn't there, the model literally cannot call it. Regenerate from canonical TOOL_SCHEMAS via python core/tool_export.py.",
    ),
    (
        "How can I make JARVIS work fully offline",
        "architecture",
        "Replace each cloud dependency with a local equivalent: Vision -> Ollama gemma3:4b. STT -> faster-whisper. TTS -> Piper. LLM brain -> already Ollama. Wake word -> Picovoice Porcupine. Web search -> DuckDuckGo HTML scrape. Keep cloud as fallback, not default.",
    ),
    (
        "JARVIS forgets I said something earlier in the conversation",
        "diagnostic",
        "Check core/database.py get_conversations_context() — it limits to max_exchanges=15. With aggressive poison filtering, the actual injected count can be lower. Increase the limit or add explicit memory entries via /api/memory/save.",
    ),
    (
        "Why does Gemini Live still work when REST API quota is dead",
        "knowledge",
        "Gemini Live runs on the BidiGenerateContent WebSocket API which has a separate quota allocation from the REST generateContent endpoint. Different daily limit, different RPM. Voice keeps working even when REST is exhausted.",
    ),
    (
        "How do I detect that local Ollama vision is available",
        "diagnostic",
        "GET http://127.0.0.1:11434/api/tags returns installed models. Then POST /api/show with each model name and check response.capabilities for 'vision'. The Python helper _pick_local_vision_model() in web/server.py does this with a preference order.",
    ),
    (
        "Tools work when typed but voice JARVIS won't call them",
        "diagnostic",
        "The Gemini Live model only sees tools in generatedToolDeclarations.json. Even if the switch handler in JarvisGeminiLive.ts has a case for it, the model never tries it because the tool declaration is missing. Run python core/tool_export.py to regenerate.",
    ),
]


# ─── 3. Tool routing SFT pairs for fine-tune ──────────────────────────────────
TOOL_ROUTING_PAIRS: list[tuple[str, str, dict]] = [
    ("can you check my screen", "screen_scan", {}),
    ("what's on my screen right now", "screen_scan", {}),
    ("look at my screen and tell me what's happening", "screen_scan", {}),
    ("scan my screen", "screen_scan", {}),
    ("can you see this", "screen_scan", {}),
    ("describe what you see on my screen", "screen_scan", {}),
    ("read my screen", "screen_scan", {}),
    ("take a screenshot and analyze it", "screen_scan", {}),
    ("what app am I in", "screen_scan", {}),
    ("can you tell me what window is active", "screen_scan", {}),
    ("read the text I just copied", "read_clipboard_image", {}),
    ("what's in my clipboard", "read_clipboard_image", {}),
    ("can you see what I copied", "read_clipboard_image", {}),
    ("research how to set up local vision in JARVIS", "research_topic", {"query": "how to set up local vision in JARVIS"}),
    ("look up Ollama vision models", "research_topic", {"query": "Ollama vision models"}),
]


def write_knowledge_graph(kg: KnowledgeGraph) -> int:
    """Insert each lesson as an entity with structured facts."""
    count = 0
    for lesson in LESSONS:
        kg.add_entity(lesson["name"], lesson["type"], lesson["facts"])
        count += 1
    return count


def write_learning_log() -> int:
    """Append diagnostic Q&A as JSONL entries."""
    count = 0
    LEARN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with LEARN_LOG.open("a", encoding="utf-8") as f:
        for question, category, answer in DIAGNOSTIC_QA:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_input": question,
                "tool_used": "diagnostic_reasoning",
                "tool_params": {"category": category},
                "response": answer,
                "success": True,
                "source": "session_lessons_2026-04-26",
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1
    return count


def write_tool_routing_sft() -> int:
    """Append (input, tool, params) SFT pairs in messages format."""
    count = 0
    SFT_LOG.parent.mkdir(parents=True, exist_ok=True)
    system_prompt = (
        "You are JARVIS, an AI desktop assistant. Your job is to understand "
        "the user's request and respond with the correct tool call as JSON. "
        "Available tools include: screen_scan, read_clipboard_image, "
        "research_topic, web_search, take_screenshot, run_terminal, "
        "open_app, read_file, write_file, send_email. Respond ONLY with a "
        "JSON object containing 'tool' and 'params' keys."
    )
    with SFT_LOG.open("a", encoding="utf-8") as f:
        for user_text, tool, params in TOOL_ROUTING_PAIRS:
            assistant = json.dumps({"tool": tool, "params": params})
            entry = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                    {"role": "assistant", "content": assistant},
                ]
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            count += 1
    return count


def write_lessons_markdown() -> int:
    """Human-readable summary for future reference."""
    LESSONS_MD.write_text(
        "# JARVIS Session Lessons — 2026-04-26\n\n"
        "Recorded automatically from a debugging session that took JARVIS\n"
        "from 'screen analysis broken' to fully-local Ollama vision pipeline.\n\n"
        "## Bugs diagnosed and fixed\n\n"
        + "\n\n".join(
            f"### {i + 1}. {lesson['name']}\n"
            f"**Type:** {lesson['type']}\n\n"
            + "\n".join(f"- **{k}:** {v}" for k, v in lesson["facts"].items())
            for i, lesson in enumerate(LESSONS)
        )
        + "\n\n## Q&A pairs added to learning log\n\n"
        + "\n".join(f"{i + 1}. **Q:** {q}\n   **A:** {a}\n" for i, (q, _, a) in enumerate(DIAGNOSTIC_QA))
        + "\n\n## Tool routing examples added to SFT dataset\n\n"
        + "\n".join(f'- `"{u}"` -> `{t}`' for u, t, _ in TOOL_ROUTING_PAIRS),
        encoding="utf-8",
    )
    return 1


def main() -> None:
    print("=" * 70)
    print(" JARVIS — Teaching session lessons (2026-04-26)")
    print("=" * 70)

    print("\n[1/4] Writing to knowledge graph...")
    kg = KnowledgeGraph()
    n_kg = write_knowledge_graph(kg)
    print(f"  -> {n_kg} entities written to knowledge graph")

    print("\n[2/4] Appending to learning log...")
    n_log = write_learning_log()
    print(f"  -> {n_log} Q&A pairs appended to {LEARN_LOG}")

    print("\n[3/4] Appending to tool routing SFT dataset...")
    n_sft = write_tool_routing_sft()
    print(f"  -> {n_sft} routing examples appended to {SFT_LOG}")

    print("\n[4/4] Writing markdown summary...")
    write_lessons_markdown()
    print(f"  -> {LESSONS_MD}")

    print("\n" + "=" * 70)
    print(" SUMMARY")
    print("=" * 70)
    print(f"  Knowledge graph entities:  {n_kg}")
    print(f"  Learning log entries:       {n_log}")
    print(f"  SFT routing examples:       {n_sft}")
    print(f"  Markdown report:            {LESSONS_MD.name}")
    print()
    print("  Next step (optional):")
    print("    cd training && python train_offline_brain.py")
    print("    -> retrains jarvis-brain Ollama model with new examples")


if __name__ == "__main__":
    main()
