"""
JARVIS — Teach reliability fixes discovered by the harness.

Acts as a teacher to JARVIS: every failure the reliability harness finds
and we fix, we record here so JARVIS LEARNS the pattern — into the
knowledge graph (recallable at runtime), the learning log (future
fine-tunes), and the tool-routing SFT dataset (so the planner picks the
right tool next time).

Re-run after each batch of fixes:  python training/teach_reliability_fixes.py

This is the self-improvement loop: harness finds failures -> we fix +
teach -> harness re-runs -> number goes up -> JARVIS remembers why.
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


# ─── Bug patterns fixed (knowledge graph entities) ────────────────────────
RELIABILITY_LESSONS = [
    {
        "name": "create_folder_misrouted_to_build_project",
        "type": "bug_pattern",
        "facts": {
            "symptom": "'create a folder called X on the desktop' failed with 'No project goal provided'",
            "root_cause": "No create_folder tool existed. The request fell through to build_project (a code-scaffolding tool) which needs a project goal.",
            "diagnosis": "POST /api/agent/execute 'create a folder...' -> tool=build_project -> 'No project goal provided'",
            "fix": "Added create_folder tool (executor._create_folder) with os.makedirs, resolves desktop/documents/downloads/home. High-specificity orchestrator pattern (score 11) so it beats build_project. Arg extraction pulls 'called X' + 'on the desktop'.",
            "fix_files": "core/tool_schemas.py, core/executor.py, core/orchestrator.py",
            "verified": "create folder harness_probe_folder -> Created folder on Desktop, exists on disk",
            "tags": "file-ops, routing, folder, build_project",
        },
    },
    {
        "name": "calculator_operator_confusion",
        "type": "bug_pattern",
        "facts": {
            "symptom": "'compute 45 times 3 plus 15' gave 78 instead of 150 — the LLM planner pressed PLUS instead of MULTIPLY for the first operator",
            "root_cause": "gemma3:4b decomposed the math but confused operator words — it mapped 'times' to the + key. Small models are unreliable at operator mapping in multi-op expressions.",
            "diagnosis": "agent steps showed 'Press plus' where 'Press multiply' was needed; Calculator displayed 78 (=45+3+15) not 150 (=45*3+15). honest_verifier CORRECTLY caught it (not a false positive).",
            "fix": "Added _try_calculator_plan() in agent_loop — for compute goals, parse the math expression DETERMINISTICALLY (regex tokenize numbers+operators, normalize word-operators to symbols, eval the expected answer ourselves) and emit the exact key sequence. Never lets the LLM guess operators. Handles times/plus/minus/divided-by AND 'X percent of Y'.",
            "fix_files": "core/agent_loop.py (_try_calculator_plan, called before _ai_decompose)",
            "verified": "45 times 3 plus 15 -> presses multiply then add -> Display is 150 VERIFIED. Also 12x12=144, 200/8=25, 15% of 240=36.",
            "lesson": "For deterministic domains (math), parse+compute in code — don't delegate to a small LLM that hallucinates operators.",
            "tags": "calculator, math, planner, operators, deterministic",
        },
    },
    {
        "name": "complex_chain_false_positives",
        "type": "bug_pattern",
        "facts": {
            "symptom": "3+ step tasks (open notepad + type + ctrl-s) report success but don't complete; honest verifier misses because it only checks the FINAL state",
            "root_cause": "honest_verifier verifies end-state (Calculator display, Notepad text) but has no per-step verification, so a chain that fails at step 2 but reaches step 3 can look done",
            "diagnosis": "reliability_harness --extreme: chain3 tasks fail with agent_claimed=True (false positive)",
            "fix_status": "PARTIAL — calculator chains now deterministic (fixed). notepad+save chains still need per-step verification.",
            "tags": "agent-loop, verification, chains, false-positive",
        },
    },
    {
        "name": "reliability_baseline_2026",
        "type": "fact",
        "facts": {
            "easy_tier": "8/8 verified (100%) — app launch, 2-step compound, OCR, screenshot, docx",
            "browser_tier": "3/3 verified (100%) — chrome opens + navigates",
            "hard_tier": "~72% — fails on UI menu clicking, multi-app chaining, 3+ step chains, folder creation (now fixed)",
            "false_positives": "0 on simple tasks, 2 on complex chains",
            "measured_by": "training/reliability_harness.py --extreme",
            "note": "The ceiling is 3+ step chains and UI element clicking. Simple-to-medium desktop tasks are production-grade.",
            "tags": "reliability, baseline, metrics",
        },
    },
]


# ─── Diagnostic Q&A for learning log ──────────────────────────────────────
DIAGNOSTIC_QA = [
    ("create a folder called projects on my desktop", "file_ops",
     "Use the create_folder tool with name='projects', location='desktop'. "
     "Do NOT use build_project (that's for code projects). create_folder "
     "does a real os.makedirs and resolves desktop/documents/downloads."),
    ("why did 'create a folder' fail before", "diagnostic",
     "There was no create_folder tool, so the request fell through to "
     "build_project which needs a code-project goal. Fixed by adding a "
     "dedicated create_folder tool with high-specificity routing."),
    ("how reliable is JARVIS at desktop tasks", "knowledge",
     "Measured baseline: 100% on easy tasks (open apps, 2-step compound, "
     "OCR, screenshots, docx), 100% on browser open/navigate, ~72% on hard "
     "tasks (UI menu clicking, multi-app chaining, 3+ step chains). Run "
     "training/reliability_harness.py --extreme to re-measure."),
]


# ─── Tool routing SFT pairs ───────────────────────────────────────────────
ROUTING_PAIRS = [
    ("create a folder called projects on the desktop", "create_folder",
     {"name": "projects", "location": "desktop"}),
    ("make a new folder named work in documents", "create_folder",
     {"name": "work", "location": "documents"}),
    ("create a directory called backup", "create_folder", {"name": "backup"}),
    ("mkdir test_folder on my desktop", "create_folder",
     {"name": "test_folder", "location": "desktop"}),
    ("make me a folder called photos", "create_folder", {"name": "photos"}),
    # Calculator math is handled by deterministic planner (not routing) but
    # teach the pattern anyway for the classifier
    ("compute 45 times 3 plus 15", "calculator_plan", {"expected": "150"}),
    ("what is 15 percent of 240", "calculator_plan", {"expected": "36"}),
]


def main():
    print("=" * 68)
    print(" JARVIS — Teaching reliability fixes")
    print("=" * 68)

    kg = KnowledgeGraph()

    print("\n[1/3] Knowledge graph lessons...")
    n = 0
    for lesson in RELIABILITY_LESSONS:
        kg.add_entity(lesson["name"], lesson["type"], lesson["facts"])
        n += 1
    print(f"  -> {n} lessons recorded")

    print("\n[2/3] Learning log Q&A...")
    LEARN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with LEARN_LOG.open("a", encoding="utf-8") as f:
        for q, cat, a in DIAGNOSTIC_QA:
            f.write(json.dumps({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "user_input": q, "tool_used": "diagnostic_reasoning",
                "tool_params": {"category": cat}, "response": a,
                "success": True, "source": "reliability_fixes",
            }, ensure_ascii=False) + "\n")
    print(f"  -> {len(DIAGNOSTIC_QA)} Q&A pairs appended")

    print("\n[3/3] Tool routing SFT pairs...")
    SFT_LOG.parent.mkdir(parents=True, exist_ok=True)
    sysmsg = ("You are JARVIS. Respond with the correct tool call as JSON "
              "with 'tool' and 'params' keys. Use create_folder for making "
              "folders/directories — never build_project.")
    with SFT_LOG.open("a", encoding="utf-8") as f:
        for user, tool, params in ROUTING_PAIRS:
            f.write(json.dumps({
                "messages": [
                    {"role": "system", "content": sysmsg},
                    {"role": "user", "content": user},
                    {"role": "assistant", "content": json.dumps({"tool": tool, "params": params})},
                ]
            }, ensure_ascii=False) + "\n")
    print(f"  -> {len(ROUTING_PAIRS)} routing examples appended")

    print("\n" + "=" * 68)
    print(f" Taught: {n} lessons, {len(DIAGNOSTIC_QA)} Q&A, {len(ROUTING_PAIRS)} routing pairs")
    print(" JARVIS now recalls the create_folder fix + reliability baseline.")
    print("=" * 68)


if __name__ == "__main__":
    main()
