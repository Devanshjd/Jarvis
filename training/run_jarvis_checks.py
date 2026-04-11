"""
Run all JARVIS regression checks.

This wraps both:
- jarvis_smoke_tests.py
- jarvis_integration_smoke_tests.py

Usage:
    python training/run_jarvis_checks.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
SCRIPTS = [
    REPO_ROOT / "training" / "jarvis_smoke_tests.py",
    REPO_ROOT / "training" / "jarvis_integration_smoke_tests.py",
]


def main() -> int:
    print("JARVIS full regression checks")
    print(f"Repo: {REPO_ROOT}")
    failures = 0

    for script in SCRIPTS:
        print(f"\n=== Running {script.name} ===")
        result = subprocess.run([PYTHON, str(script)], cwd=str(REPO_ROOT))
        if result.returncode != 0:
            failures += 1

    if failures:
        print(f"\nOverall result: {len(SCRIPTS) - failures}/{len(SCRIPTS)} suites passed")
        return 1

    print(f"\nOverall result: {len(SCRIPTS)}/{len(SCRIPTS)} suites passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
