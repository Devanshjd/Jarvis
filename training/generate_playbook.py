"""
JARVIS — Playbook Generator

The realistic version of "feed JARVIS everything it needs to know how to
use itself." We can't retrain a foundation model (that's Google/Anthropic
scale) — but we CAN teach JARVIS how to HANDLE the situations it'll face.

This generates a large, curated dataset of (situation -> correct approach
-> tool sequence -> reasoning) across every category JARVIS handles, then
feeds it into all three learning surfaces:
  1. SFT dataset  -> fine-tune jarvis-brain (tool routing)
  2. Knowledge graph -> runtime recall (how to handle X)
  3. Learning log -> future training

Each PLAYBOOK entry = a situation with multiple phrasing variants + the
correct tool + reasoning. The generator expands phrasings into SFT pairs.

Run:  python training/generate_playbook.py
Then: cd training && python train_offline_brain.py   (bake into jarvis-brain)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.knowledge_graph import KnowledgeGraph  # noqa: E402

LEARN_LOG = ROOT / "training" / "learning_log.jsonl"
SFT_LOG = ROOT / "training" / "datasets" / "jarvis_tool_routing" / "jarvis_tool_routing_sft.jsonl"
PLAYBOOK_MD = ROOT / "training" / "JARVIS_PLAYBOOK.md"


# ═══════════════════════════════════════════════════════════════════════
#  THE PLAYBOOK — how JARVIS should handle each situation
#  Each: situation, category, phrasings[], tool, args_template, reasoning
# ═══════════════════════════════════════════════════════════════════════

PLAYBOOK = [
    # ── FILE & FOLDER OPERATIONS ─────────────────────────────────────
    {
        "situation": "create a folder", "category": "file_ops",
        "tool": "create_folder",
        "phrasings": [
            "create a folder called {X}", "make a folder named {X}",
            "make me a new folder called {X}", "create a directory named {X}",
            "new folder called {X}", "mkdir {X}",
            "create a folder called {X} on the desktop",
        ],
        "args": {"name": "{X}"},
        "reasoning": "Use create_folder (NOT build_project — that's for code). Default location is Desktop.",
        "fillers": ["projects", "work", "photos", "backup", "documents_2026"],
    },
    {
        "situation": "create a Word document", "category": "file_ops",
        "tool": "write_docx",
        "phrasings": [
            "create a word file called {X}", "make a word document about {X}",
            "write a report called {X}", "save this as a word doc named {X}",
            "create a docx called {X}",
        ],
        "args": {"filename": "{X}"},
        "reasoning": "Use write_docx for real Word files (NOT write_file, which makes plain text/markdown).",
        "fillers": ["meeting_notes", "report", "summary", "letter", "proposal"],
    },
    {
        "situation": "create a spreadsheet", "category": "file_ops",
        "tool": "write_xlsx",
        "phrasings": [
            "create an excel file called {X}", "make a spreadsheet named {X}",
            "save this as excel called {X}", "create a xlsx named {X}",
        ],
        "args": {"filename": "{X}"},
        "reasoning": "Use write_xlsx for real Excel files with proper cells.",
        "fillers": ["budget", "inventory", "data", "expenses", "schedule"],
    },
    {
        "situation": "find files", "category": "file_ops",
        "tool": "find_files",
        "phrasings": [
            "find all {X} files", "search for files named {X}",
            "find files with {X} in the name", "locate {X} files",
        ],
        "args": {"pattern": "{X}"},
        "reasoning": "Use find_files with a name pattern. Not a web search.",
        "fillers": ["pdf", "python", "readme", "invoice", "backup"],
    },

    # ── APPLICATION CONTROL ──────────────────────────────────────────
    {
        "situation": "open an application", "category": "app_control",
        "tool": "open_app",
        "phrasings": [
            "open {X}", "launch {X}", "start {X}", "run {X}", "open up {X}",
        ],
        "args": {"app": "{X}"},
        "reasoning": "Use open_app with the app name. Works for notepad, calculator, chrome, paint, etc.",
        "fillers": ["notepad", "calculator", "chrome", "paint", "file explorer", "spotify"],
    },

    # ── CALCULATOR / MATH (deterministic — handled in code) ──────────
    {
        "situation": "compute math", "category": "math",
        "tool": "calculator_plan",
        "phrasings": [
            "compute {X}", "what is {X}", "calculate {X}", "work out {X}",
        ],
        "args": {},
        "reasoning": "Math goes to the deterministic calculator planner — parse the expression in code, press exact keys. Never let the LLM guess operators (it confuses times/plus).",
        "fillers": ["45 times 3 plus 15", "200 divided by 8", "15 percent of 240",
                    "12 times 12", "100 minus 37"],
    },

    # ── SCREEN AWARENESS ─────────────────────────────────────────────
    {
        "situation": "read text on screen", "category": "screen",
        "tool": "read_screen_text",
        "phrasings": [
            "read the text on my screen", "what does the screen say",
            "read all the text on screen", "capture the text on screen",
            "OCR my screen",
        ],
        "args": {},
        "reasoning": "Use read_screen_text (Tesseract OCR) — fast, accurate for pure text. NEVER route to send_msg.",
        "fillers": [""],
    },
    {
        "situation": "describe the screen", "category": "screen",
        "tool": "screen_scan",
        "phrasings": [
            "what's on my screen", "describe my screen", "look at my screen",
            "what am I looking at", "can you see my screen",
        ],
        "args": {},
        "reasoning": "Use screen_scan (vision LLM) when the user wants understanding/reasoning about the screen, not just raw text.",
        "fillers": [""],
    },
    {
        "situation": "take a screenshot", "category": "screen",
        "tool": "take_screenshot",
        "phrasings": [
            "take a screenshot", "capture my screen", "grab a screenshot",
            "screenshot this",
        ],
        "args": {},
        "reasoning": "Use take_screenshot. Saves to Desktop.",
        "fillers": [""],
    },

    # ── WEB ──────────────────────────────────────────────────────────
    {
        "situation": "web search", "category": "web",
        "tool": "web_search",
        "phrasings": [
            "search for {X}", "google {X}", "look up {X} online",
            "search the web for {X}", "find information about {X}",
        ],
        "args": {"query": "{X}"},
        "reasoning": "Use web_search for online lookups.",
        "fillers": ["raspberry pi 5 specs", "weather in London", "python tutorials",
                    "latest AI news", "how to solder"],
    },

    # ── SYSTEM CONTROL ───────────────────────────────────────────────
    {
        "situation": "lock the screen", "category": "system",
        "tool": "lock_screen",
        "phrasings": ["lock my computer", "lock the screen", "lock my pc"],
        "args": {},
        "reasoning": "Use lock_screen for security.",
        "fillers": [""],
    },
    {
        "situation": "set volume", "category": "system",
        "tool": "set_volume",
        "phrasings": [
            "set volume to {X}", "change volume to {X} percent",
            "turn the volume to {X}",
        ],
        "args": {"level": "{X}"},
        "reasoning": "Use set_volume with a 0-100 level.",
        "fillers": ["50", "30", "75", "20", "100"],
    },

    # ── VOICE OUTPUT ─────────────────────────────────────────────────
    {
        "situation": "speak aloud", "category": "voice",
        "tool": "speak_locally",
        "phrasings": [
            "say {X} out loud", "speak {X}", "announce {X}", "read this aloud: {X}",
        ],
        "args": {"text": "{X}"},
        "reasoning": "Use speak_locally (Piper TTS) — local, no cloud. NOT send_msg.",
        "fillers": ["hello", "the task is done", "time for a break", "good morning"],
    },

    # ── MEMORY ───────────────────────────────────────────────────────
    {
        "situation": "remember something", "category": "memory",
        "tool": "remember",
        "phrasings": [
            "remember that {X}", "note that {X}", "keep in mind that {X}",
            "save this: {X}",
        ],
        "args": {"text": "{X}"},
        "reasoning": "Use remember to store a fact. (Memory is also auto-extracted from conversation.)",
        "fillers": ["my wifi password is in the drawer", "the meeting is at 3pm",
                    "John prefers email", "the API key expires next month"],
    },

    # ── SECURITY / PENTEST (the user's domain) ───────────────────────
    {
        "situation": "scan a URL", "category": "security",
        "tool": "url_scan",
        "phrasings": [
            "scan {X}", "check if {X} is safe", "analyze the url {X}",
        ],
        "args": {"url": "{X}"},
        "reasoning": "Use url_scan for URL threat analysis.",
        "fillers": ["example.com", "suspicious-site.net", "test.org"],
    },
    {
        "situation": "port scan a host", "category": "security",
        "tool": "port_scan",
        "phrasings": [
            "port scan {X}", "scan ports on {X}", "check open ports on {X}",
        ],
        "args": {"host": "{X}"},
        "reasoning": "Use port_scan for network reconnaissance (authorized targets only).",
        "fillers": ["192.168.1.1", "scanme.nmap.org", "localhost"],
    },
]


# ═══════════════════════════════════════════════════════════════════════
#  SITUATION-HANDLING PRINCIPLES (how to THINK, not just route)
#  These teach reasoning patterns — the "how to sort this situation" layer.
# ═══════════════════════════════════════════════════════════════════════

PRINCIPLES = [
    {
        "name": "principle_ambiguous_request",
        "situation": "The user's request is ambiguous or underspecified",
        "how_to_handle": "Don't guess wildly. If a single reasonable interpretation exists, act on it and state the assumption. If genuinely unclear (which file? which contact?), ask ONE concise clarifying question rather than doing the wrong thing.",
    },
    {
        "name": "principle_deterministic_over_llm",
        "situation": "A task has a deterministic correct answer (math, exact string, file path)",
        "how_to_handle": "Compute it in code, don't let the small LLM guess. Math -> parse+eval. Sequential 'X then Y' -> split deterministically. The LLM is for fuzzy judgment, not arithmetic or exact operations.",
    },
    {
        "name": "principle_verify_dont_assume",
        "situation": "You performed an action and want to report success",
        "how_to_handle": "Verify by reading the real world (window title, app field, file on disk) — never trust that 'the tool returned' means 'the goal was achieved'. If you can't verify, say 'done, but I couldn't confirm' — never claim success you can't prove.",
    },
    {
        "name": "principle_focus_before_typing",
        "situation": "About to type or click into an app",
        "how_to_handle": "Make sure the TARGET window is focused first. Typing into the wrong window is the #1 cause of silent failures. Bring the app to foreground, confirm, then type.",
    },
    {
        "name": "principle_wrong_tool_recovery",
        "situation": "A tool failed or returned an error",
        "how_to_handle": "Don't just retry the same thing. Diagnose: wrong tool? wrong args? wrong window focused? Then adapt — switch tool, fix args, or fall back to a different approach. Persistence with adaptation, not blind repetition.",
    },
    {
        "name": "principle_chain_never_drop_steps",
        "situation": "A request has multiple actions ('do X then Y then Z')",
        "how_to_handle": "Split on connectors and execute EVERY action. Small LLMs silently drop steps — count the actions in the request and make sure the plan has at least that many steps.",
    },
    {
        "name": "principle_privacy_local_first",
        "situation": "A task could be done locally or via cloud",
        "how_to_handle": "Prefer local (Ollama, Tesseract, Piper) — it's private, free, and works offline. Only use cloud when local genuinely can't do it. This is core to JARVIS's identity and the military-grade requirement.",
    },
    {
        "name": "principle_dont_send_msg_for_screen",
        "situation": "Request mentions 'read', 'text', or content but is about the SCREEN",
        "how_to_handle": "'read the text on my screen' -> read_screen_text, NEVER send_msg. send_msg is ONLY for messaging a contact on WhatsApp/Telegram. Check for messaging keywords (send, to, message) before ever routing to send_msg.",
    },
]


def expand_phrasings():
    """Expand playbook entries into concrete (user_text, tool, args) SFT pairs."""
    pairs = []
    for entry in PLAYBOOK:
        fillers = entry.get("fillers", [""])
        for phrasing in entry["phrasings"]:
            if "{X}" in phrasing:
                for filler in fillers:
                    user = phrasing.replace("{X}", filler).strip()
                    args = {k: (v.replace("{X}", filler) if isinstance(v, str) else v)
                            for k, v in entry.get("args", {}).items()}
                    pairs.append((user, entry["tool"], args, entry["reasoning"]))
            else:
                pairs.append((phrasing, entry["tool"], entry.get("args", {}), entry["reasoning"]))
    return pairs


def main():
    print("=" * 68)
    print(" JARVIS PLAYBOOK GENERATOR")
    print(" Teaching JARVIS how to USE its abilities across situations")
    print("=" * 68)

    kg = KnowledgeGraph()
    pairs = expand_phrasings()

    # ── 1. SFT dataset ──────────────────────────────────────────────
    print(f"\n[1/4] Tool-routing SFT pairs...")
    SFT_LOG.parent.mkdir(parents=True, exist_ok=True)
    sysmsg = ("You are JARVIS, a desktop AI assistant. Given the user's "
              "request, respond with the correct tool call as JSON with "
              "'tool' and 'params' keys. Pick the most specific correct tool.")
    with SFT_LOG.open("a", encoding="utf-8") as f:
        for user, tool, args, _ in pairs:
            f.write(json.dumps({
                "messages": [
                    {"role": "system", "content": sysmsg},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": json.dumps({"tool": tool, "params": args})},
                ]
            }, ensure_ascii=False) + "\n")
    print(f"  -> {len(pairs)} routing examples")

    # ── 2. Knowledge graph — situations + principles ────────────────
    print(f"\n[2/4] Knowledge graph playbook entries...")
    n_kg = 0
    for entry in PLAYBOOK:
        kg.add_entity(
            f"handle_{entry['situation'].replace(' ', '_')}",
            "playbook",
            {
                "situation": entry["situation"],
                "category": entry["category"],
                "correct_tool": entry["tool"],
                "reasoning": entry["reasoning"],
            },
        )
        n_kg += 1
    for p in PRINCIPLES:
        kg.add_entity(p["name"], "principle", {
            "situation": p["situation"],
            "how_to_handle": p["how_to_handle"],
        })
        n_kg += 1
    print(f"  -> {n_kg} playbook + principle entities")

    # ── 3. Learning log — principles as Q&A ─────────────────────────
    print(f"\n[3/4] Learning log (reasoning principles)...")
    LEARN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with LEARN_LOG.open("a", encoding="utf-8") as f:
        for p in PRINCIPLES:
            f.write(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_input": p["situation"],
                "tool_used": "reasoning_principle",
                "tool_params": {"name": p["name"]},
                "response": p["how_to_handle"],
                "success": True, "source": "playbook",
            }, ensure_ascii=False) + "\n")
    print(f"  -> {len(PRINCIPLES)} principles")

    # ── 4. Human-readable playbook doc ──────────────────────────────
    print(f"\n[4/4] Markdown playbook...")
    lines = ["# JARVIS Playbook — How to Handle Situations\n",
             "Auto-generated. How JARVIS should use its tools + how to think.\n",
             "\n## Situation → Tool routing\n"]
    by_cat = {}
    for e in PLAYBOOK:
        by_cat.setdefault(e["category"], []).append(e)
    for cat, entries in sorted(by_cat.items()):
        lines.append(f"\n### {cat}\n")
        for e in entries:
            lines.append(f"- **{e['situation']}** → `{e['tool']}` — {e['reasoning']}")
    lines.append("\n## Reasoning principles (how to think)\n")
    for p in PRINCIPLES:
        lines.append(f"\n**{p['situation']}**\n{p['how_to_handle']}\n")
    PLAYBOOK_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"  -> {PLAYBOOK_MD}")

    print("\n" + "=" * 68)
    print(f" PLAYBOOK GENERATED")
    print(f"   {len(pairs)} SFT routing examples")
    print(f"   {n_kg} knowledge-graph entities (situations + principles)")
    print(f"   {len(PRINCIPLES)} reasoning principles")
    print("=" * 68)
    print("\n Next: cd training && python train_offline_brain.py")
    print(" -> bakes the playbook into the jarvis-brain model")


if __name__ == "__main__":
    main()
