"""
Proactive-signals tests — the rails that make ambient help safe.

Codex asked for dedup, opt-out, and no-action; the privacy (content-free) and
persona-gate checks matter just as much:
  · default OFF — nothing surfaces until a source is opted in,
  · opt-out — a disabled source is never even observed (no side effect),
  · content-free — a screen signal carries a COUNT + summary, never a screenshot/
    OCR/title,
  · dedup — a persistent incident keeps one stable id,
  · no-action — signals are suggestions (questions), never commands,
  · Persona `proactivity:off` is a hard master gate.

Run:  python training/test_proactive_signals.py
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.proactive_signals import Consent, collect


def _consent(tmp, **on) -> Consent:
    c = Consent(Path(tmp) / "proactive.json")
    for src, val in on.items():
        c.set(src, val)
    return c


def test_default_off() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d)                                    # nothing opted in
        r = collect(c, {"screen_errors": lambda: {"count": 9}})
        assert r["enabled"] is False and r["signals"] == [], "off by default"


def test_opt_out_source_is_never_observed() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d)                                    # screen_errors OFF
        calls = []
        r = collect(c, {"screen_errors": lambda: (calls.append(1), {"count": 9})[1]})
        assert r["signals"] == [] and calls == [], \
            "a disabled source must not be observed or surfaced (no side effect)"


def test_opt_in_yields_an_attributable_signal() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d, screen_errors=True)
        r = collect(c, {"screen_errors": lambda: {"count": 5}})
        assert len(r["signals"]) == 1
        s = r["signals"][0]
        assert s["source"] == "screen_errors" and s["severity"] == "medium"
        assert "5 times" in s["summary"], "the reason must be attributable"


def test_signals_are_content_free() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d, screen_errors=True)
        r = collect(c, {"screen_errors": lambda: {"count": 6}})
        blob = json.dumps(r).lower()
        for leak in ("screenshot", "ocr", "window", "pixel", "clipboard"):
            assert leak not in blob, f"signal leaked '{leak}'"
        assert set(r["signals"][0]) == {"id", "source", "severity", "observed_at",
                                        "summary", "suggestion"}, "only descriptive fields"


def test_dedup_stable_id_for_persistent_incident() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d, screen_errors=True)
        prov = {"screen_errors": lambda: {"count": 5}}
        first = collect(c, prov)["signals"][0]["id"]
        again = collect(c, prov)["signals"][0]["id"]
        assert first == again, "the same ongoing incident must keep one id"


def test_no_action_only_suggestions() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d, screen_errors=True, battery=True)
        r = collect(c, {"screen_errors": lambda: {"count": 9},
                        "battery": lambda: {"percent": 8, "discharging": True}})
        assert len(r["signals"]) == 2
        for s in r["signals"]:
            assert not any(k in s for k in ("action", "execute", "command", "run")), \
                "a signal must never carry an action"
            assert s["suggestion"].endswith("?"), "it offers/asks — never commands"


def test_persona_off_is_a_hard_gate() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d, screen_errors=True)
        r = collect(c, {"screen_errors": lambda: {"count": 9}}, proactivity="off")
        assert r["enabled"] is False and r["signals"] == [], \
            "Persona proactivity:off must surface nothing, even if opted in"


def test_battery_thresholds() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d, battery=True)
        assert collect(c, {"battery": lambda: {"percent": 8, "discharging": True}})["signals"]
        assert collect(c, {"battery": lambda: {"percent": 8, "discharging": False}})["signals"] == [], \
            "plugged in → no signal"
        assert collect(c, {"battery": lambda: {"percent": 50, "discharging": True}})["signals"] == [], \
            ">=25% → no signal"


def test_severity_ladder() -> None:
    with tempfile.TemporaryDirectory() as d:
        c = _consent(d, screen_errors=True)

        def sev(n):
            sig = collect(c, {"screen_errors": lambda: {"count": n}})["signals"]
            return sig[0]["severity"] if sig else None

        assert sev(2) is None, "below threshold → nothing"
        assert sev(3) == "low" and sev(5) == "medium" and sev(8) == "high"


def main() -> None:
    tests = [
        ("default off", test_default_off),
        ("opt-out source never observed", test_opt_out_source_is_never_observed),
        ("opt-in yields attributable signal", test_opt_in_yields_an_attributable_signal),
        ("signals are content-free", test_signals_are_content_free),
        ("dedup stable id", test_dedup_stable_id_for_persistent_incident),
        ("no-action, only suggestions", test_no_action_only_suggestions),
        ("persona off is a hard gate", test_persona_off_is_a_hard_gate),
        ("battery thresholds", test_battery_thresholds),
        ("severity ladder", test_severity_ladder),
    ]
    print("=" * 64)
    print(" PROACTIVE-SIGNALS TESTS")
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
