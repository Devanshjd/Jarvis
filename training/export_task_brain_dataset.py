"""
Export JARVIS task-brain data into training-friendly datasets.

Usage:
    python training/export_task_brain_dataset.py
    python training/export_task_brain_dataset.py --output training_data
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.task_brain import TaskBrain  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Export JARVIS task-brain datasets.")
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "training_data",
        help="Output directory for generated dataset files.",
    )
    args = parser.parse_args()

    brain = TaskBrain()
    result = brain.export_datasets(args.output)

    print("JARVIS task dataset exported")
    print(f"- Episodes: {result['episodes']}")
    print(f"- Planner examples: {result['planner_examples']}")
    print(f"- Procedures: {result['procedures']}")
    print(f"- Output: {result['output_dir']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
