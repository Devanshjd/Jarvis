"""
Cross-device handoff tests — a safe, tiny "continue over there" marker.

Proves the lifecycle: start → the target device sees it → ack clears it. Plus
target filtering (a phone handoff isn't shown to the laptop) and single-use ack.

Run:  python training/test_handoff.py
"""
from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.handoff import HandoffStore


def _store(d) -> HandoffStore:
    return HandoffStore(Path(d) / "handoff.json")


def test_start_pickup_ack_lifecycle() -> None:
    with tempfile.TemporaryDirectory() as d:
        s = _store(d)
        assert s.latest() is None, "nothing pending at first"
        h = s.start("phone", from_device="laptop", summary="You: hi · JARVIS: hello", note="")
        assert h["to"] == "phone" and h["from"] == "laptop" and h["acked"] is False
        got = s.latest("phone")
        assert got and got["id"] == h["id"] and "hello" in got["summary"]
        assert s.ack(h["id"]) is True
        assert s.latest("phone") is None, "an acked handoff is no longer pending"
        assert s.ack(h["id"]) is False, "can't ack twice"


def test_target_filtering() -> None:
    with tempfile.TemporaryDirectory() as d:
        s = _store(d)
        s.start("phone", from_device="laptop", summary="x")
        assert s.latest("phone") is not None, "phone sees a phone-targeted handoff"
        assert s.latest("laptop") is None, "laptop must NOT pick up a phone handoff"
        assert s.latest() is not None, "no filter → returns the pending one"


def test_new_handoff_replaces_previous() -> None:
    with tempfile.TemporaryDirectory() as d:
        s = _store(d)
        first = s.start("laptop", summary="one")
        second = s.start("phone", summary="two")
        cur = s.latest()
        assert cur["id"] == second["id"] and cur["id"] != first["id"]
        assert cur["to"] == "phone"


def test_summary_and_note_are_bounded() -> None:
    with tempfile.TemporaryDirectory() as d:
        s = _store(d)
        h = s.start("phone", summary="x" * 999, note="y" * 999)
        assert len(h["summary"]) <= 400 and len(h["note"]) <= 200


def main() -> None:
    tests = [
        ("start → pickup → ack lifecycle", test_start_pickup_ack_lifecycle),
        ("target filtering", test_target_filtering),
        ("new handoff replaces previous", test_new_handoff_replaces_previous),
        ("summary/note bounded", test_summary_and_note_are_bounded),
    ]
    print("=" * 64)
    print(" CROSS-DEVICE HANDOFF TESTS")
    print("=" * 64)
    passed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as exc:
            import traceback
            print(f"  [FAIL] {name} -> {exc}")
            traceback.print_exc()
    print(f"\n  {passed}/{len(tests)} passed")
    sys.exit(0 if passed == len(tests) else 1)


if __name__ == "__main__":
    main()
