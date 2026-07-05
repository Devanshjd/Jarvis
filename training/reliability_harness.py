"""
J.A.R.V.I.S — Reliability Harness

Measures the ACTUAL proficiency of JARVIS's tools, not just whether they
exist. Runs a battery of real PC-control tasks, verifies each outcome
INDEPENDENTLY (reads actual app state, not the agent's self-report), and
reports a success-rate PERCENTAGE per category.

This is the answer to "how reliable is your agent?" — a number, not a guess.
Run it before and after changes to see if proficiency went up or down.

Philosophy (learned from watching false positives this session):
  - The agent's "success" claim is NOT trusted
  - Every task is verified by reading the real world (window titles, app
    field contents, files on disk) via honest_verifier + pywinauto
  - UNVERIFIABLE ≠ SUCCESS — it counts as "unknown", reported separately
  - Non-destructive tasks only (won't send messages, delete files, etc.)

Usage:
    python training/reliability_harness.py           # run full battery
    python training/reliability_harness.py --quick   # run a fast subset

Output: per-category + overall success rate, plus training/reliability_report.json
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BACKEND = "http://127.0.0.1:8765"


# ═══════════════════════════════════════════════════════════════════════
#  Verification primitives — read the REAL world, don't trust the agent
# ═══════════════════════════════════════════════════════════════════════

def verify_window_open(title_substr: str) -> bool:
    """True if a window whose title contains title_substr is open."""
    try:
        from core.context_awareness import get_context
        ctx = get_context()
        return ctx.find_window(title_substr) is not None
    except Exception:
        return False


def verify_calc_shows(expected: str) -> str:
    """VERIFIED/FAILED/UNKNOWN — does Calculator display `expected`?"""
    try:
        from core.honest_verifier import verify_calculator_display, Verdict
        r = verify_calculator_display(expected)
        return r.verdict.value
    except Exception:
        return "unknown"


def verify_notepad_has(expected: str) -> str:
    """VERIFIED/FAILED/UNKNOWN — does Notepad contain `expected`?"""
    try:
        from core.honest_verifier import verify_notepad_text, Verdict
        r = verify_notepad_text(expected)
        return r.verdict.value
    except Exception:
        return "unknown"


def verify_file_exists(path_substr: str) -> bool:
    """True if a file matching path_substr exists on Desktop or Documents."""
    for base in (Path.home() / "Desktop", Path.home() / "Documents", Path.home()):
        try:
            for p in base.glob("*"):
                if path_substr.lower() in p.name.lower():
                    return True
        except Exception:
            continue
    return False


def close_app(image_name: str):
    """Best-effort close of an app by process image name (cleanup between tests)."""
    try:
        subprocess.run(["taskkill", "/IM", image_name, "/F"],
                       capture_output=True, timeout=5)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════
#  Agent invocation
# ═══════════════════════════════════════════════════════════════════════

def run_agent(goal: str, timeout: float = 120.0) -> dict:
    """Send a goal to /api/agent/execute, return parsed result."""
    body = json.dumps({
        "goal": goal, "approve_desktop": True,
        "wait_for_complete": True, "timeout_s": timeout,
    }).encode()
    req = urllib.request.Request(
        f"{BACKEND}/api/agent/execute", data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout + 20) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════
#  Test battery — (category, goal, verify_fn) — NON-DESTRUCTIVE only
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class TestCase:
    category: str
    name: str
    goal: str
    verify: callable            # returns "verified"/"failed"/"unknown" or bool
    cleanup: list = field(default_factory=list)   # process image names to kill first
    wait_after: float = 2.0


TEST_BATTERY = [
    # ── App launching ────────────────────────────────────────────────
    TestCase("app_launch", "open notepad",
             "open notepad",
             lambda: verify_window_open("notepad"),
             cleanup=["notepad.exe"]),
    TestCase("app_launch", "open calculator",
             "open calculator",
             lambda: verify_window_open("calculator"),
             cleanup=["CalculatorApp.exe", "Calculator.exe"]),

    # ── Multi-step compound tasks ────────────────────────────────────
    TestCase("compound", "notepad + type text",
             "open notepad and type reliability test alpha",
             lambda: verify_notepad_has("reliability test alpha"),
             cleanup=["notepad.exe"], wait_after=3.0),
    TestCase("compound", "calc 12 x 12",
             "open calculator and compute 12 times 12",
             lambda: verify_calc_shows("144"),
             cleanup=["CalculatorApp.exe", "Calculator.exe"], wait_after=3.0),
    TestCase("compound", "calc 200 / 8",
             "open calculator and compute 200 divided by 8",
             lambda: verify_calc_shows("25"),
             cleanup=["CalculatorApp.exe", "Calculator.exe"], wait_after=3.0),

    # ── Screen reading (OCR) ─────────────────────────────────────────
    TestCase("screen_read", "read screen text",
             "read all the text on my screen",
             # Verify: agent returned non-trivial text
             None),  # special-cased below

    # ── File operations ──────────────────────────────────────────────
    TestCase("file_ops", "create word doc",
             "create a word file called reliability_probe with hello content",
             lambda: verify_file_exists("reliability_probe"),
             wait_after=2.0),

    # ── Direct queries (no app) ──────────────────────────────────────
    TestCase("query", "screenshot",
             "take a screenshot",
             lambda: verify_file_exists("screenshot"),
             wait_after=2.0),
]


def evaluate(tc: TestCase, agent_result: dict) -> str:
    """Return 'verified' / 'failed' / 'unknown' for a test case."""
    # Special case: screen_read — check the agent output has real text
    if tc.category == "screen_read":
        steps = agent_result.get("steps", []) or []
        for s in steps:
            out = (s.get("result") or "")
            if "chars" in out.lower() and len(out) > 60:
                return "verified"
        return "failed"

    if tc.verify is None:
        return "unknown"

    try:
        result = tc.verify()
    except Exception:
        return "unknown"

    if isinstance(result, bool):
        return "verified" if result else "failed"
    return str(result)  # already verified/failed/unknown


def main():
    quick = "--quick" in sys.argv
    battery = TEST_BATTERY[:4] if quick else TEST_BATTERY

    print("═" * 70)
    print(" JARVIS RELIABILITY HARNESS")
    print(" Measures ACTUAL success rate — verified by reading real app state")
    print("═" * 70)

    # Confirm backend is up
    try:
        urllib.request.urlopen(f"{BACKEND}/api/agent/status", timeout=5)
    except Exception:
        print("\n❌ Backend not running. Start it first:")
        print("   cd 'D:\\my pross\\Jarvis'; python web_main.py")
        return

    results = []
    for i, tc in enumerate(battery, 1):
        print(f"\n[{i}/{len(battery)}] {tc.category} :: {tc.name}")
        print(f"    goal: {tc.goal!r}")
        for proc in tc.cleanup:
            close_app(proc)
        if tc.cleanup:
            time.sleep(0.6)

        t0 = time.time()
        agent_result = run_agent(tc.goal)
        elapsed = time.time() - t0
        agent_claimed = bool(agent_result.get("success"))

        time.sleep(tc.wait_after)
        verdict = evaluate(tc, agent_result)

        icon = {"verified": "✅", "failed": "❌", "unknown": "❓"}[verdict]
        flag = ""
        if agent_claimed and verdict == "failed":
            flag = "  ⚠️ FALSE POSITIVE (agent claimed success)"
        print(f"    {icon} {verdict.upper()} ({elapsed:.1f}s) | agent_claimed={agent_claimed}{flag}")

        results.append({
            "category": tc.category, "name": tc.name, "goal": tc.goal,
            "verdict": verdict, "agent_claimed_success": agent_claimed,
            "elapsed_s": round(elapsed, 1),
        })

    # ── Scorecard ────────────────────────────────────────────────────
    print("\n" + "═" * 70)
    print(" PROFICIENCY SCORECARD")
    print("═" * 70)

    from collections import defaultdict
    cat_stats = defaultdict(lambda: {"verified": 0, "failed": 0, "unknown": 0, "total": 0})
    false_positives = 0
    for r in results:
        c = cat_stats[r["category"]]
        c[r["verdict"]] += 1
        c["total"] += 1
        if r["agent_claimed_success"] and r["verdict"] == "failed":
            false_positives += 1

    print(f"\n  {'Category':<16} {'Verified':<10} {'Rate':<8} {'Failed':<8} {'Unknown'}")
    print(f"  {'-'*16} {'-'*10} {'-'*8} {'-'*8} {'-'*8}")
    total_v = total_f = total_u = total_n = 0
    for cat, s in sorted(cat_stats.items()):
        # Rate = verified / (verified + failed), excluding unknowns
        denom = s["verified"] + s["failed"]
        rate = f"{100*s['verified']//denom}%" if denom else "n/a"
        print(f"  {cat:<16} {s['verified']:<10} {rate:<8} {s['failed']:<8} {s['unknown']}")
        total_v += s["verified"]; total_f += s["failed"]
        total_u += s["unknown"]; total_n += s["total"]

    overall_denom = total_v + total_f
    overall_rate = f"{100*total_v//overall_denom}%" if overall_denom else "n/a"
    print(f"  {'-'*16} {'-'*10} {'-'*8} {'-'*8} {'-'*8}")
    print(f"  {'OVERALL':<16} {total_v}/{total_n:<8} {overall_rate:<8} {total_f:<8} {total_u}")

    print(f"\n  ⚠️  FALSE POSITIVES (agent lied about success): {false_positives}")
    print(f"  ❓ UNKNOWN (couldn't verify — NOT counted as success): {total_u}")

    print("\n  Honest read:")
    if overall_denom:
        pct = 100 * total_v // overall_denom
        if pct >= 90:
            print(f"    {pct}% verified success — production-grade for these tasks.")
        elif pct >= 70:
            print(f"    {pct}% verified success — usable, but {total_f} real failures to fix.")
        else:
            print(f"    {pct}% verified success — NOT reliable yet. {total_f} failures need work.")
    if false_positives:
        print(f"    {false_positives} false positives = the agent can't be trusted to self-report.")

    # Save
    report_path = ROOT / "training" / "reliability_report.json"
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "overall_rate": overall_rate,
        "verified": total_v, "failed": total_f, "unknown": total_u,
        "false_positives": false_positives,
        "by_category": {k: dict(v) for k, v in cat_stats.items()},
        "results": results,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  Report saved: {report_path}")
    print("  Re-run after changes to track whether proficiency improved.")


if __name__ == "__main__":
    main()
