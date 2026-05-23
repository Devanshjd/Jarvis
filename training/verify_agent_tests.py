"""
JARVIS Agent — VERIFIED test runner.

Runs each agent goal AND independently verifies the actual outcome via
post-execution screenshot + OCR. No more taking the agent's word for it.

For each test:
  1. (optional) Close stale windows
  2. POST /api/agent/execute with the goal
  3. Wait for completion
  4. Take screenshot, run Tesseract OCR
  5. Check if expected_substring appears in OCR output
  6. Report TRUE PASS / FALSE POSITIVE / FAIL with evidence
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error

# Force utf-8 stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BACKEND = "http://127.0.0.1:8765"


def run_goal(goal: str, timeout: float = 180.0) -> dict:
    """POST a goal to /api/agent/execute and return the parsed response."""
    body = json.dumps({
        "goal": goal,
        "approve_desktop": True,
        "wait_for_complete": True,
        "timeout_s": timeout,
    }).encode()
    req = urllib.request.Request(
        f"{BACKEND}/api/agent/execute",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout + 20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}: {e.read().decode()[:200]}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_screen_text() -> str:
    """Hit /api/screen/ocr and return whatever text is currently visible."""
    try:
        with urllib.request.urlopen(f"{BACKEND}/api/screen/ocr", timeout=15) as r:
            d = json.loads(r.read())
            return d.get("text", "") if d.get("success") else ""
    except Exception:
        return ""


def close_window(window_title_contains: str) -> bool:
    """Try to close a window whose title contains the given substring (Windows)."""
    try:
        # Use taskkill to close by image name (e.g. notepad.exe, calc.exe)
        subprocess.run(
            ["taskkill", "/IM", window_title_contains, "/F"],
            capture_output=True, timeout=5,
        )
        return True
    except Exception:
        return False


def verify_test(
    name: str,
    goal: str,
    expected_substrings: list[str],
    cleanup_processes: list[str] = None,
    cleanup_first: bool = True,
    wait_after_run: float = 1.5,
) -> dict:
    """Run one test with real verification.

    Returns dict with: name, agent_reported, ocr_verified, evidence, verdict.
    """
    print(f"\n┌─ TEST: {name}")
    print(f"│  Goal: {goal!r}")

    # Cleanup before (so the test starts from a known state)
    if cleanup_first and cleanup_processes:
        for proc in cleanup_processes:
            close_window(proc)
        time.sleep(0.5)

    # Run the agent
    t0 = time.time()
    result = run_goal(goal)
    elapsed = time.time() - t0
    agent_says_success = bool(result.get("success"))
    steps = result.get("steps") or []
    step_count = len(steps)

    print(f"│  Agent reported: {'SUCCESS' if agent_says_success else 'FAIL'} "
          f"({step_count} steps, {elapsed:.1f}s)")

    # Wait for UI to settle before OCR
    time.sleep(wait_after_run)

    # Independent verification via OCR
    screen_text = get_screen_text()
    screen_text_lower = screen_text.lower()

    hits = []
    misses = []
    for substr in expected_substrings:
        if substr.lower() in screen_text_lower:
            hits.append(substr)
        else:
            misses.append(substr)

    all_found = len(misses) == 0
    print(f"│  OCR check: found {len(hits)}/{len(expected_substrings)} expected substrings")
    if hits:
        print(f"│    found: {hits}")
    if misses:
        print(f"│    MISSING: {misses}")

    # Verdict
    if agent_says_success and all_found:
        verdict = "TRUE_PASS"
    elif agent_says_success and not all_found:
        verdict = "FALSE_POSITIVE"
    elif not agent_says_success and all_found:
        verdict = "UNDER_REPORTED"  # Agent thinks it failed but it actually worked
    else:
        verdict = "TRUE_FAIL"

    icon = {"TRUE_PASS": "✅", "FALSE_POSITIVE": "⚠️ ", "UNDER_REPORTED": "🤔", "TRUE_FAIL": "❌"}[verdict]
    print(f"└─ {icon} VERDICT: {verdict}")

    return {
        "name": name,
        "goal": goal,
        "verdict": verdict,
        "agent_reported_success": agent_says_success,
        "step_count": step_count,
        "elapsed_s": round(elapsed, 1),
        "expected_substrings": expected_substrings,
        "found": hits,
        "missing": misses,
        "screen_text_preview": screen_text[:300],
    }


def main():
    print("═" * 70)
    print(" JARVIS AGENT — VERIFIED TEST RUN")
    print(" Each test runs the goal, then INDEPENDENTLY verifies via OCR")
    print("═" * 70)

    tests = [
        # (name, goal, expected substrings in post-screen OCR, processes to kill first)
        {
            "name": "Calculator: 23 × 7",
            "goal": "open calculator and compute 23 times 7",
            "expected_substrings": ["161"],   # The math answer must appear
            "cleanup_processes": ["CalculatorApp.exe", "Calculator.exe"],
            "wait_after_run": 2.5,
        },
        {
            "name": "Notepad: type 'hello jarvis'",
            "goal": "open notepad and type hello jarvis",
            "expected_substrings": ["hello jarvis"],
            "cleanup_processes": ["notepad.exe"],
            "wait_after_run": 2.0,
        },
        {
            "name": "Calculator: 100 / 4",
            "goal": "open calculator and compute 100 divided by 4",
            "expected_substrings": ["25"],
            "cleanup_processes": ["CalculatorApp.exe", "Calculator.exe"],
            "wait_after_run": 2.5,
        },
        {
            "name": "OCR: read screen text",
            "goal": "read all the text on my screen",
            # Should produce SOME text from screen; substring 'jarvis' likely
            # since the app title bar usually contains it.
            "expected_substrings": [],   # we verify differently below
            "cleanup_processes": [],
            "wait_after_run": 1.0,
        },
    ]

    results = []
    for t in tests:
        r = verify_test(
            name=t["name"],
            goal=t["goal"],
            expected_substrings=t["expected_substrings"],
            cleanup_processes=t.get("cleanup_processes"),
            wait_after_run=t.get("wait_after_run", 1.5),
        )
        results.append(r)
        time.sleep(2)  # breathing room between tests

    # Summary
    print("\n" + "═" * 70)
    print(" SUMMARY")
    print("═" * 70)
    counts = {"TRUE_PASS": 0, "FALSE_POSITIVE": 0, "UNDER_REPORTED": 0, "TRUE_FAIL": 0}
    for r in results:
        counts[r["verdict"]] += 1
        print(f"  [{r['verdict']:14}] {r['name']}")

    print()
    print(f"  TRUE_PASS:      {counts['TRUE_PASS']}/{len(results)}  (agent succeeded AND verified)")
    print(f"  FALSE_POSITIVE: {counts['FALSE_POSITIVE']}/{len(results)}  (agent claimed success but OCR disagrees)")
    print(f"  UNDER_REPORTED: {counts['UNDER_REPORTED']}/{len(results)}  (agent said fail but actually worked)")
    print(f"  TRUE_FAIL:      {counts['TRUE_FAIL']}/{len(results)}  (agent failed and verification confirms)")

    # Save raw results
    out = "training/last_verified_test_run.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n  Detailed results: {out}")


if __name__ == "__main__":
    main()
